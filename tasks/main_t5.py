# coding=utf-8
# Copyright (c) 2020, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Main tasks functionality."""

import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__),
                                             os.path.pardir)))

from megatron import get_args
from megatron.initialize import initialize_megatron


def get_tasks_args(parser):
    """Provide extra arguments required for tasks."""
    group = parser.add_argument_group(title='tasks')

    group.add_argument('--task', type=str, required=True,
                       help='Task name.')
    group.add_argument('--epochs', type=int, default=None,
                       help='Number of finetunning epochs. Zero results in '
                       'evaluation only.')
    group.add_argument('--pretrained-checkpoint', type=str, default=None,
                       help='Pretrained checkpoint used for finetunning.')
    group.add_argument('--keep-last', action='store_true',
                       help='Keep the last batch (maybe incomplete) in'
                       'the data loader')
    group.add_argument('--train-data', nargs='+', default=None,
                       help='Whitespace separated paths or corpora names '
                       'for training.')
    group.add_argument('--valid-data', nargs='*', default=None,
                       help='path(s) to the validation data.')
    group.add_argument('--test-data', nargs='*', default=None,
                       help='path(s) to the test data.')
    group.add_argument('--beam-size', default=1, type=int,
                       help='Beam size to use for decoding. '
                            'A beam size of 1 corresponds to greedy search')
    group.add_argument('--max-decode-len', default=512, type=int,
                       help='maximum sequence length to generate at the decoder.')
    group.add_argument('--overlapping-eval', type=int, default=32,
                       help='Sliding window for overlapping evaluation.')
    group.add_argument('--strict-lambada', action='store_true',
                       help='Use more difficult formulation of lambada.')
    group.add_argument('--eval-batch-size', type=int, default=None,
                       help='Eval Batch size per model instance (local batch size). '
                            'Global batch size is local batch size times data '
                            'parallel size.')
    group.add_argument('--sample-rate', type=float, default=1.0,
                       help='sample rate for training data. Supposed to be 0 < sample_rate < 1')
    return parser


if __name__ == '__main__':

    initialize_megatron(extra_args_provider=get_tasks_args)

    args = get_args()
    if args.task == 'RACE':
        raise NotImplementedError('Task {} is not implemented.'.format(
            args.task))
    elif args.task in ['MNLI']:
        from glue.t5.finetune import main
    elif args.task == 'CNNDM':
        from summarization.t5.finetune import main
    elif args.task in ['LAMBADA', 'WIKITEXT103']:
        raise NotImplementedError('Task {} is not implemented.'.format(
            args.task))
    else:
        raise NotImplementedError('Task {} is not implemented.'.format(
            args.task))
    main()
