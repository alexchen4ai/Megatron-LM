# Copyright (c) 2022, NVIDIA CORPORATION. All rights reserved.

"""BERT Style dataset."""

import numpy as np
import torch

from megatron import (
    get_args,
    get_tokenizer,
    mpu,
    print_rank_0
)
from megatron.data.dataset_utils import (
    get_samples_mapping,
    get_a_and_b_segments,
    truncate_segments,
    create_tokens_and_tokentypes,
    create_masked_lm_predictions
)

# >>>
from lutil import pax
# <<<

class BertDataset(torch.utils.data.Dataset):

    def __init__(self, name, indexed_dataset, data_prefix,
                 num_epochs, max_num_samples, masked_lm_prob,
                 max_seq_length, short_seq_prob, seed, binary_head):

        # >>>
        # raise Exception("hi.")
        # <<<

        # Params to store.
        self.name = name
        self.seed = seed
        self.masked_lm_prob = masked_lm_prob
        self.max_seq_length = max_seq_length
        self.binary_head = binary_head

        # Dataset.
        self.indexed_dataset = indexed_dataset

        # >>>
        pax(0, {
            "indexed_dataset / dir" : dir(indexed_dataset),
            # "indexed_dataset / __dict__" :
            # list(indexed_dataset.__dict__.keys()),
            "indexed_dataset" : {
                # "thing" : dir(indexed_dataset),
                "0" : indexed_dataset[0],
                "1" : indexed_dataset[1],
                "2" : indexed_dataset[2],
                "Index" : indexed_dataset.Index,
                "ty" : type(indexed_dataset).__name__,
                # "_index" : indexed_dataset._index,
                "doc_idx" : indexed_dataset.doc_idx,
                "sizes" : indexed_dataset.sizes,
            },
        })
        # <<<

        # Build the samples mapping.
        # >>>
        # raise Exception("hi.")
        # <<<
        self.samples_mapping = get_samples_mapping(self.indexed_dataset,
                                                   data_prefix,
                                                   num_epochs,
                                                   max_num_samples,
                                                   self.max_seq_length - 3, # account for added tokens
                                                   short_seq_prob,
                                                   self.seed,
                                                   self.name,
                                                   self.binary_head)
        # >>>
        # raise Exception("hi.")
        # pax({"samples_mapping": self.samples_mapping})
        # <<<

        # >>>
        # if torch.distributed.get_rank() == 0:
        #     print(self.samples_mapping[:100])
        # pax(0, {
        #     # "indexed_dataset" : self.indexed_dataset,
        #     "samples_mapping" : self.samples_mapping,
        #     "samples_mapping / 0" : self.samples_mapping[0],
        # })
        # <<<

        # Vocab stuff.
        tokenizer = get_tokenizer()
        self.vocab_id_list = list(tokenizer.inv_vocab.keys())
        self.vocab_id_to_token_dict = tokenizer.inv_vocab
        self.cls_id = tokenizer.cls
        self.sep_id = tokenizer.sep
        self.mask_id = tokenizer.mask
        self.pad_id = tokenizer.pad

    def __len__(self):
        return self.samples_mapping.shape[0]

    def __getitem__(self, idx):
        start_idx, end_idx, seq_length = self.samples_mapping[idx]
        sample = [self.indexed_dataset[i] for i in range(start_idx, end_idx)]
        # Note that this rng state should be numpy and not python since
        # python randint is inclusive whereas the numpy one is exclusive.
        # We % 2**32 since numpy requres the seed to be between 0 and 2**32 - 1
        np_rng = np.random.RandomState(seed=((self.seed + idx) % 2**32))
        # >>>
        pax(0, {
            "start_idx" : int(start_idx),
            "end_idx" : int(end_idx),
            "seq_length" : int(seq_length),
            "indexed_dataset / %d" % start_idx : self.indexed_dataset[start_idx],
            "sample" : sample,
            "seed" : self.seed,
            # "seq_length" : seq_length,
            # "max_seq_length" : self.max_seq_length,
            # "vocab_id_list" : self.vocab_id_list,
            # "vocab_id_to_token_dict" : self.vocab_id_to_token_dict,
            # "cls_id" : self.cls_id,
            # "sep_id" : self.sep_id,
            # "mask_id" : self.mask_id,
            # "pad_id" : self.pad_id,
            # "masked_lm_prob" : self.masked_lm_prob,
            # "np_rng" : np_rng,
            # "binary_head" : self.binary_head,
        })
        # <<<
        return build_training_sample(sample, seq_length,
                                     self.max_seq_length,  # needed for padding
                                     self.vocab_id_list,
                                     self.vocab_id_to_token_dict,
                                     self.cls_id, self.sep_id,
                                     self.mask_id, self.pad_id,
                                     self.masked_lm_prob, np_rng,
                                     self.binary_head)




def build_training_sample(sample,
                          target_seq_length, max_seq_length,
                          vocab_id_list, vocab_id_to_token_dict,
                          cls_id, sep_id, mask_id, pad_id,
                          masked_lm_prob, np_rng, binary_head):
    """Biuld training sample.

    Arguments:
        sample: A list of sentences in which each sentence is a list token ids.
        target_seq_length: Desired sequence length.
        max_seq_length: Maximum length of the sequence. All values are padded to
            this length.
        vocab_id_list: List of vocabulary ids. Used to pick a random id.
        vocab_id_to_token_dict: A dictionary from vocab ids to text tokens.
        cls_id: Start of example id.
        sep_id: Separator id.
        mask_id: Mask token id.
        pad_id: Padding token id.
        masked_lm_prob: Probability to mask tokens.
        np_rng: Random number genenrator. Note that this rng state should be
              numpy and not python since python randint is inclusive for
              the opper bound whereas the numpy one is exclusive.
    """

    if binary_head:
        # We assume that we have at least two sentences in the sample
        assert len(sample) > 1
    assert target_seq_length <= max_seq_length

    # Divide sample into two segments (A and B).
    if binary_head:
        tokens_a, tokens_b, is_next_random = get_a_and_b_segments(sample,
                                                                  np_rng)
    else:
        tokens_a = []
        for j in range(len(sample)):
            tokens_a.extend(sample[j])
        tokens_b = []
        is_next_random = False

    # Truncate to `target_sequence_length`.
    max_num_tokens = target_seq_length
    truncated = truncate_segments(tokens_a, tokens_b, len(tokens_a),
                                  len(tokens_b), max_num_tokens, np_rng)

    # Build tokens and toketypes.
    tokens, tokentypes = create_tokens_and_tokentypes(tokens_a, tokens_b,
                                                      cls_id, sep_id)
    # >>>
    # print("[r%d] **** sample %d, tokens_a %d, tokens_b %d, tokens %d." % (
    #     torch.distributed.get_rank(),
    #     len(sample[0]),
    #     len(tokens_a),
    #     len(tokens_b),
    #     len(tokens),
    # ))
    # <<<

    # Masking.
    max_predictions_per_seq = masked_lm_prob * max_num_tokens
    (tokens, masked_positions, masked_labels, _, _) = create_masked_lm_predictions(
        tokens, vocab_id_list, vocab_id_to_token_dict, masked_lm_prob,
        cls_id, sep_id, mask_id, max_predictions_per_seq, np_rng)

    # >>>
    # print("[r%d] **** tokens %d." % (torch.distributed.get_rank(), len(tokens)))
    # <<<

    # Padding.
    tokens_np, tokentypes_np, labels_np, padding_mask_np, loss_mask_np \
        = pad_and_convert_to_numpy(tokens, tokentypes, masked_positions,
                                   masked_labels, pad_id, max_seq_length)

    train_sample = {
        'text': tokens_np,
        'types': tokentypes_np,
        'labels': labels_np,
        'is_random': int(is_next_random),
        'loss_mask': loss_mask_np,
        'padding_mask': padding_mask_np,
        'truncated': int(truncated)}
    return train_sample


def pad_and_convert_to_numpy(tokens, tokentypes, masked_positions,
                             masked_labels, pad_id, max_seq_length):
    """Pad sequences and convert them to numpy."""

    # Some checks.
    num_tokens = len(tokens)
    padding_length = max_seq_length - num_tokens
    # >>>
    # assert padding_length >= 0
    assert padding_length >= 0, f"tokens {len(tokens)}, max {max_seq_length}."
    # pax({"pad_id": pad_id})
    # <<<
    assert len(tokentypes) == num_tokens
    assert len(masked_positions) == len(masked_labels)

    # Tokens and token types.
    filler = [pad_id] * padding_length
    tokens_np = np.array(tokens + filler, dtype=np.int64)
    tokentypes_np = np.array(tokentypes + filler, dtype=np.int64)

    # Padding mask.
    padding_mask_np = np.array([1] * num_tokens + [0] * padding_length,
                               dtype=np.int64)

    # Lables and loss mask.
    labels = [-1] * max_seq_length
    loss_mask = [0] * max_seq_length
    for i in range(len(masked_positions)):
        assert masked_positions[i] < num_tokens
        labels[masked_positions[i]] = masked_labels[i]
        loss_mask[masked_positions[i]] = 1
    labels_np = np.array(labels, dtype=np.int64)
    loss_mask_np = np.array(loss_mask, dtype=np.int64)

    return tokens_np, tokentypes_np, labels_np, padding_mask_np, loss_mask_np
