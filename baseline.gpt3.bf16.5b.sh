#!/bin/bash

#SBATCH -p luna -A adlr -t 04:00:00 --nodes=20 --exclusive --mem=0 --overcommit --ntasks-per-node=8 --dependency=singleton --job-name=adlr-nlp:develop:baseline.gpt3.bf16.5b

NAME="baseline.gpt3.bf16/5b"

DATETIME=`date +'date_%y-%m-%d_time_%H-%M-%S'`

DIR="/lustre/fsw/adlr/adlr-nlp/jkamalu/fp8/${NAME}"

# Megatron-LM main branch commit SHA f5345dfac5060afb86dad1d1926eb05d005e57f7 from 2021/10/29
MEGATRON_DIR="/lustre/fsw/adlr/adlr-nlp/jkamalu/fp8/megatron-lm-main"

LOG_DIR="${DIR}/logs"
CHECKPOINT_DIR="${DIR}/checkpoints"
TENSORBOARD_DIR="${DIR}/tensorboard"

mkdir -p ${LOG_DIR}
mkdir -p ${CHECKPOINT_DIR}
mkdir -p ${TENSORBOARD_DIR}

# Get the data blend
. /lustre/fsw/adlr/adlr-nlp-large/data/gpt3/gpt3_blend.sh

BPE_DIR="/lustre/fsw/adlr/adlr-nlp-large/data/bpe"

options=" \
    --exit-duration-in-mins 230 \
    --tensor-model-parallel-size 4 \
    --pipeline-model-parallel-size 1 \
    --num-layers 24 \
    --hidden-size 4096 \
    --num-attention-heads 32 \
    --seq-length 2048 \
    --max-position-embeddings 2048 \
    --micro-batch-size 4 \
    --global-batch-size 1280 \
    --train-samples 192000000 \
    --lr-decay-samples 166400000 \
    --lr 1.2e-4 \
    --min-lr 1.2e-5 \
    --lr-decay-style cosine \
    --log-interval 100 \
    --eval-iters 50 \
    --eval-interval 2000 \
    --data-path ${DATA_BLEND} \
    --vocab-file ${BPE_DIR}/gpt2-vocab.json \
    --merge-file ${BPE_DIR}/gpt2-merges.txt \
    --save-interval 100 \
    --save ${CHECKPOINT_DIR} \
    --load ${CHECKPOINT_DIR} \
    --split 9999,1,0 \
    --clip-grad 1.0 \
    --weight-decay 0.1 \
    --adam-beta1 0.9 \
    --adam-beta2 0.95 \
    --init-method-std 0.014 \
    --log-params-norm \
    --log-num-zeros-in-grad \
    --bf16 \
    --DDP-impl local \
    --tensorboard-dir ${TENSORBOARD_DIR} \
    --activations-checkpoint-method uniform \
    --lr-warmup-samples 244141"
#   --rampup-batch-size 32 32 2929688 \

run_cmd="${MEGATRON_DIR}/bind.sh --cpu=${MEGATRON_DIR}/dgxa100_ccx.sh --mem=${MEGATRON_DIR}/dgxa100_ccx.sh python -u ${MEGATRON_DIR}/pretrain_gpt.py ${options}"

srun -l \
     --container-image "/lustre/fsw/adlr/adlr-nlp/images/pytorch+bf16_nccl_fusion+pyspy.sqsh" \
     --container-mounts "/lustre/fsw/adlr:/lustre/fsw/adlr" \
     --output=$LOG_DIR/%x_%j_$DATETIME.log sh -c "${run_cmd}"

set +x

