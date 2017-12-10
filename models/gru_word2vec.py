import numpy as np

import torch
import torch.nn as nn
from torch.autograd import Variable

import pyjet.backend as J

from .abstract_word2vec import AWord2Vec
from . import register_model_func


class GRUWord2Vec(AWord2Vec):
    """
    Class that represents the vanilla word2vec module. We'll swap this out with our experimental modules.

    this contains the actual trainable pytorch module and houses the parameters of the model. This model
    should not be trained directly, but rather through the `Word2Vec` class below.
    """

    def __init__(self, vocab_size, embedding_size, char2id, bidirectional=False, sparse=False, **kwargs):
        """
        Initializes a pytorch word2vec module.

        :param vocab_size: The size of the vocabulary of the corpus
        :param embedding_size: The dimension of the embeddings
        :param char2id: A mapping of each character in the vocabulary to its respective id
        :param bidirectional: Whether or not to make the GRU bidirectional
        """
        super(GRUWord2Vec, self).__init__(vocab_size, embedding_size)
        self.char2id = char2id
        self.num_chars = len(self.char2id)
        self.bidirectional = bidirectional

        # Make a one-hot encoder
        self._char_encoder = nn.Embedding(self.num_chars+1, self.num_chars, padding_idx=self.num_chars)
        torch.diag(torch.ones(self.num_chars), out=self._char_encoder.weight.data[:-1])
        # Freeze the encodings
        self._char_encoder.weight.requires_grad = False

        self._encoder = nn.GRU(self.num_chars, embedding_size // 2 if bidirectional else embedding_size, 1, batch_first=True,
                               bidirectional=self.bidirectional)
        # Use sparse for more memory efficient computations
        # Note that only SGD will work with sparse embedding layers on a GPU
        self._decoder = nn.Embedding(self.vocab_size, self.embedding_size, sparse=sparse)
        self._decoder.weight.data.zero_()

        self._embedding_norms = None

        if J.use_cuda:
            self.cuda()

    def chartoken2tensor(self, tokens):
        """Helper to cast a list of tokens to a torch LongTensor"""
        assert tokens.ndim == 2

        charids = [[self.char2id[char] for char in token.text] for token in tokens.flatten()]
        seq_lens = [len(charid_array) for charid_array in charids]
        # Create the padded one hot encodings
        max_seq_len = max(seq_lens)
        # B*W x L
        charids = Variable(J.LongTensor(
            [charid_array + [self.num_chars] * (max_seq_len - len(charid_array)) for charid_array in charids]))
        # Get the one hot encodings
        onehots = self._char_encoder(charids)  # B*W x L x C
        assert onehots.size(0) == tokens.shape[0] * tokens.shape[1]

        return onehots, seq_lens

    def lookup(self, token):
        return self.lookup_tokens(np.array([[token]]))

    def lookup_tokens(self, tokens):
        # Shape of tokens is B x W
        tokens = np.array(tokens)
        # create the one-hot char encodings
        # B*W x L x C
        char_encodings, seq_lens = self.chartoken2tensor(tokens)
        outputs, _ = self._encoder(char_encodings)
        new_outputs = J.zeros(outputs.size(0), outputs.size(2))
        # Fill it in
        for seq_len in seq_lens:
            new_outputs = outputs[:, seq_len-1]
        outputs = new_outputs.view(tokens.shape[0], tokens.shape[1], self.embedding_size)
        # Select the last encoding and reshape into B x W
        # outputs = outputs[:, seq_lens-1, :].view(tokens.shape[0], tokens.shape[1], self.embedding_size)
        return outputs

    @property
    def embedding_norms(self):
        raise NotImplementedError()

    def similarities(self, tensor):
        raise NotImplementedError()


class PoolGRUWord2Vec(GRUWord2Vec):

    def __init__(self, vocab_size, embedding_size, char2id, bidirectional=True, sparse=True, **kwargs):
        super(PoolGRUWord2Vec, self).__init__(vocab_size, embedding_size, char2id, bidirectional, sparse=sparse, **kwargs)

    def lookup_tokens(self, tokens):
        # Shape of tokens is B x W
        tokens = np.array(tokens)
        # create the one-hot char encodings
        # B*W x L x C
        char_encodings, seq_lens = self.chartoken2tensor(tokens)
        outputs, _ = self._encoder(char_encodings)  # B*W x L x E
        # print(outputs.size())
        outputs = torch.max(outputs, dim=1)[0].view(tokens.shape[0], tokens.shape[1], self.embedding_size)
        return outputs


register_model_func(GRUWord2Vec)
register_model_func(PoolGRUWord2Vec)
