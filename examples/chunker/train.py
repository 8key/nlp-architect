# ******************************************************************************
# Copyright 2017-2018 Intel Corporation
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
# ******************************************************************************

from __future__ import division, print_function, unicode_literals, absolute_import

import pickle
from os import path

from neon.backends import gen_backend
from neon.callbacks.callbacks import Callbacks
from neon.layers import GeneralizedCost
from neon.optimizers.optimizer import RMSProp
from neon.transforms.cost import CrossEntropyMulti
from neon.util.argparser import NeonArgparser, extract_valid_args
from nlp_architect.data.conll2000 import CONLL2000
from nlp_architect.models.chunker import SequenceChunker
from nlp_architect.utils.io import validate_existing_filepath, validate_parent_exists, validate
from nlp_architect.utils.metrics import get_conll_scores


def validate_input_args():
    validate((args.sentence_len, int, 1, 1000))
    validate((args.lstm_depth, int, 1, 10))
    validate((args.lstm_hidden_size, int, 1, 10000))
    validate((args.token_embedding_size, int, 1, 10000))
    validate((args.pos_embedding_size, int, 1, 1000))
    validate((args.vocab_size, int, 1, 100000000))
    validate((args.char_hidden_size, int, 1, 1000))
    validate((args.max_char_word_length, int, 1, 100))
    m_path = path.join(path.dirname(path.realpath(__file__)), str(args.model_name))
    s_path = path.join(path.dirname(path.realpath(__file__)), str(args.settings))
    validate_parent_exists(m_path)
    validate_parent_exists(s_path)
    return m_path, s_path


if __name__ == '__main__':
    parser = NeonArgparser()
    parser.add_argument('--embedding_model', type=validate_existing_filepath,
                        help='word embedding model path (only GloVe and Fasttext are supported')
    parser.add_argument('--use_pos', default=False, action='store_true',
                        help='Use part-of-speech tags of tokens')
    parser.add_argument('--use_char_rnn', default=False, action='store_true',
                        help='Use char-RNN features of tokens')
    parser.add_argument('--sentence_len', default=100, type=int,
                        help='Sentence token length')
    parser.add_argument('--lstm_depth', default=1, type=int,
                        help='Deep BiLSTM depth')
    parser.add_argument('--lstm_hidden_size', default=100, type=int,
                        help='LSTM cell hidden vector size')
    parser.add_argument('--token_embedding_size', default=50, type=int,
                        help='Token embedding vector size')
    parser.add_argument('--pos_embedding_size', default=25, type=int,
                        help='Part-of-speech embedding vector size')
    parser.add_argument('--vocab_size', default=25000, type=int,
                        help='Vocabulary size to use (only if pre-trained embedding is not used)')
    parser.add_argument('--char_hidden_size', default=25, type=int,
                        help='Char-RNN cell hidden vector size')
    parser.add_argument('--max_char_word_length', default=20, type=int,
                        help='max characters per one word')
    parser.add_argument('--model_name', default='chunker', type=str,
                        help='Model file name')
    parser.add_argument('--settings', default='chunker_settings', type=str,
                        help='Model settings file name')
    parser.add_argument('--print_np_perf', default=False, action='store_true',
                        help='Print Noun Phrase (NP) tags accuracy')

    args = parser.parse_args(gen_be=False)
    model_path, settings_path = validate_input_args()

    if args.use_pos:
        pos_vocab_size = 50
    else:
        pos_vocab_size = None
    if args.use_char_rnn:
        char_vocab_size = 82
    else:
        char_vocab_size = None
    be = gen_backend(**extract_valid_args(args, gen_backend))

    dataset = CONLL2000(sentence_length=args.sentence_len,
                        vocab_size=args.vocab_size,
                        use_pos=args.use_pos,
                        use_chars=args.use_char_rnn,
                        chars_len=args.max_char_word_length,
                        embedding_model_path=args.embedding_model)
    train_set = dataset.train_iter
    test_set = dataset.test_iter

    model = SequenceChunker(sentence_length=args.sentence_len,
                            num_labels=dataset.y_size,
                            token_vocab_size=args.vocab_size,
                            pos_vocab_size=pos_vocab_size,
                            char_vocab_size=char_vocab_size,
                            max_char_word_length=args.max_char_word_length,
                            token_embedding_size=args.token_embedding_size,
                            pos_embedding_size=args.pos_embedding_size,
                            char_embedding_size=args.char_hidden_size,
                            lstm_hidden_size=args.lstm_hidden_size,
                            num_lstm_layers=args.lstm_depth,
                            use_external_embedding=args.embedding_model)

    cost = GeneralizedCost(costfunc=CrossEntropyMulti(usebits=True))
    optimizer = RMSProp(stochastic_round=args.rounding)
    callbacks = Callbacks(model.get_model(), eval_set=test_set, **args.callback_args)
    model.fit(train_set,
              optimizer=optimizer,
              epochs=args.epochs,
              cost=cost,
              callbacks=callbacks)

    # save model
    model_settings = {'sentence_len': args.sentence_len,
                      'use_embeddings': args.embedding_model is not None,
                      'pos': args.use_pos,
                      'char_rnn': args.use_char_rnn,
                      'y_vocab': dataset.y_vocab,
                      'vocabs': dataset.vocabs}

    with open(settings_path + '.dat', 'wb') as fp:
        pickle.dump(model_settings, fp)
    model.save(model_path)

    # tagging accuracy
    y_preds = model.predict(test_set)
    shape = (test_set.nbatches, args.batch_size, args.sentence_len)
    predictions = y_preds.argmax(2) \
        .reshape(shape) \
        .transpose(1, 0, 2) \
        .reshape(-1, args.sentence_len)
    truth_labels = test_set.y.reshape(-1, args.sentence_len)

    eval_report = get_conll_scores(predictions, truth_labels, {
        v + 1: k for k, v in dataset.y_vocab.items()})
    if args.print_np_perf is True:
        print('NP performance: {}'.format(eval_report[1]['NP']))
    else:
        print('Global performance: {}'.format(eval_report[0]))
