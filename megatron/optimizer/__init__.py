# Copyright (c) 2022, NVIDIA CORPORATION. All rights reserved.

from apex.optimizers import FusedAdam as Adam
from apex.optimizers import FusedSGD as SGD

from megatron import get_args, print_rank_0

from .distrib_optimizer import DistributedOptimizer
from .grad_scaler import ConstantGradScaler, DynamicGradScaler
from .optimizer import Float16OptimizerWithFloat16Params, FP32Optimizer


def get_param_groups(modules, visual_modules,
                     no_weight_decay_cond,
                     scale_lr_cond,
                     lr_mult):
    """creates param groups based on weight decay condition (regularized vs non regularized)
       and learning rate scale condition (args.lr vs lr_mult * args.lr)
       scale_lr_cond is used during finetuning where head of the network requires a scaled
       version of the base learning rate.
    """
    wd_no_scale_lr = []
    wd_scale_lr = []
    no_wd_no_scale_lr = []
    no_wd_scale_lr = []

    args = get_args()
    all_modules = modules

    if visual_modules is not None:
        all_modules = all_modules + visual_modules

    for module in all_modules:
        for name, param in module.named_parameters():
            if not param.requires_grad:
                continue

            if no_weight_decay_cond is not None:
                no_wd = no_weight_decay_cond(name, param)
            else:
                # do not regularize biases nor Norm parameters
                no_wd = name.endswith(".bias") or len(param.shape) == 1

            if scale_lr_cond is not None:
                scale_lr = scale_lr_cond(name, param)
            else:
                scale_lr = False

            if "vision" in name or "affine" in name: # PerceiverResampler parameters
                param_name = "pretraining"
            elif "xattn" in name or "inter" in name: # GatedXattnLayer parameters
                param_name = "pretraining"
            elif "gate" in name: # Gate parameters:
                param_name = "pretraining"
            elif "input_norm" in name and "language_model.encoder" in name:
                if args.align_to_old and not args.freeze_ViT:
                    param_name = "Visual"
                else:
                    param_name = "pretraining"
            elif "language_model" in name:
                param_name = "LM"
            elif "neck" in name:
                param_name = "sam_neck"
            else:
                param_name = "Visual"

            if args.freeze_ViT and param_name == "Visual":
                if 'adaptor' not in name:
                    continue
                elif not args.train_adaptor:
                    continue
                # print_rank_0('Adaptor is now being trained for {}'.format(name))

            if args.freeze_LM and param_name == "LM":
                if 'adaptor' not in name:
                    continue
                elif not args.train_adaptor:
                    continue

            print_rank_0("trainable:" + name + ": " + param_name)

            if not no_wd and not scale_lr:
                wd_no_scale_lr.append(param)
            elif not no_wd and scale_lr:
                wd_scale_lr.append(param)
            elif no_wd and not scale_lr:
                no_wd_no_scale_lr.append(param)
            else:
                no_wd_scale_lr.append(param)

    if not args.freeze_ViT and not args.freeze_LM:
        print_rank_0(f"Optimizing the whole model:")
    else:
        if args.freeze_ViT:
            print_rank_0(f"Visual Encoder is frozen.")
        if args.freeze_LM:
            print_rank_0(f"LM layers are frozen.")


    param_groups = []
    if len(wd_no_scale_lr):
        param_groups.append({'params': wd_no_scale_lr, 'wd_mult': 1.0, 'lr_mult': 1.0})
    if len(wd_scale_lr):
        param_groups.append({'params': wd_scale_lr, 'wd_mult': 1.0, 'lr_mult': lr_mult})
    if len(no_wd_no_scale_lr):
        param_groups.append({'params': no_wd_no_scale_lr, 'wd_mult': 0.0, 'lr_mult': 1.0})
    if len(no_wd_scale_lr):
        param_groups.append({'params': no_wd_scale_lr, 'wd_mult': 0.0, 'lr_mult': lr_mult})

    return param_groups

def get_megatron_optimizer(model, visual_model=None,
                           no_weight_decay_cond=None,
                           scale_lr_cond=None,
                           lr_mult=1.0):
    args = get_args()

    # Base optimizer.
    param_groups = get_param_groups(model, visual_model,
                                    no_weight_decay_cond,
                                    scale_lr_cond,
                                    lr_mult)

    if args.optimizer == 'adam':
        optimizer = Adam(param_groups,
                         lr=args.lr,
                         weight_decay=args.weight_decay,
                         betas=(args.adam_beta1, args.adam_beta2),
                         eps=args.adam_eps)
    elif args.optimizer == 'sgd':
        optimizer = SGD(param_groups,
                        lr=args.lr,
                        weight_decay=args.weight_decay,
                        momentum=args.sgd_momentum)
    else:
        raise Exception('{} optimizer is not supported.'.format(
            args.optimizer))

    # Determine whether the params have main-grad field.
    params_have_main_grad = False
    if args.DDP_impl == 'local':
        params_have_main_grad = True

    # Mixed precision optimizer.
    # - Note: both the Float16Optimizer and the DistributedOptimizer inherit
    #   from the MixedPrecisionOptimizer, which manages any optimizer where
    #   the model params and main params are distinct.
    if args.fp16 or args.bf16 or args.use_distributed_optimizer:

        # Grad scaler:
        #    if loss-scale is provided, instantiate the constant scaler.
        #    if we are using fp16 and loss-scale is not present, use a
        #       dynamic scaler.
        #    otherwise we are running in bf16 with no loss-scale so
        #       leave it as None.
        grad_scaler = None

        # Constant loss scale.
        if args.loss_scale:
            grad_scaler = ConstantGradScaler(args.loss_scale)

        # Dynamic loss scale.
        else:
            if args.fp16:
                grad_scaler = DynamicGradScaler(
                    initial_scale=args.initial_loss_scale,
                    min_scale=args.min_loss_scale,
                    growth_factor=2.0,
                    backoff_factor=0.5,
                    growth_interval=args.loss_scale_window,
                    hysteresis=args.hysteresis)

        # Megatron optimizer.
        opt_ty = DistributedOptimizer \
            if args.use_distributed_optimizer else \
            Float16OptimizerWithFloat16Params
        return opt_ty(optimizer,
                      args.clip_grad,
                      args.log_num_zeros_in_grad,
                      params_have_main_grad,
                      args.use_contiguous_buffers_in_local_ddp,
                      args.fp16,
                      args.bf16,
                      args.params_dtype,
                      grad_scaler,
                      model, visual_model=visual_model[0])

    # FP32.
    return FP32Optimizer(optimizer, args.clip_grad,
                         args.log_num_zeros_in_grad,
                         params_have_main_grad,
                         args.use_contiguous_buffers_in_local_ddp,
                         model, visual_model=visual_model[0])
