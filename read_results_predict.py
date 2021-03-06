import numpy as np
import json
import os
from keras.callbacks import EarlyStopping, ModelCheckpoint
from keras.models import Model
from keras.layers import Lambda, BatchNormalization, GaussianNoise, CuDNNLSTM,LSTM, Input, Embedding, Dropout, Bidirectional, GRU, CuDNNGRU, TimeDistributed, Dense
from AttentionWithContext import AttentionWithContext
from keras import regularizers
from sklearn.metrics import mean_squared_error
from keras import backend as K
from keras import regularizers
from sklearn.metrics import mean_squared_error
import sys

# = = = = = = = = = = = = = = =

is_GPU = True

path_root = '..'
path_to_data = path_root + '/data/'
path_to_code = path_root + '/code/'
sys.path.insert(0, path_to_code)

# = = = = = = = = = = = = = = =

from AttentionWithContext import AttentionWithContext

def bidir_lstm(my_seq,n_units,is_GPU):
    '''
    just a convenient wrapper for bidirectional RNN with GRU units
    enables CUDA acceleration on GPU
    # regardless of whether training is done on GPU, model can be loaded on CPU
    # see: https://github.com/keras-team/keras/pull/9112
    '''
    if is_GPU:
        return Bidirectional(CuDNNLSTM(units=n_units,
                                      return_sequences=True),
                             merge_mode='concat', weights=None)(my_seq)
    else:
        return Bidirectional(LSTM(units=n_units,
                                     activation='tanh',
                                     dropout=0.0,
                                     recurrent_dropout=0.0,
                                     implementation=1,
                                     return_sequences=True,
                                     recurrent_activation='sigmoid'),
                                 merge_mode='concat', weights=None)(my_seq)

def bidir_gru(my_seq,n_units,is_GPU):
    '''
    just a convenient wrapper for bidirectional RNN with GRU units
    enables CUDA acceleration on GPU
    # regardless of whether training is done on GPU, model can be loaded on CPU
    # see: https://github.com/keras-team/keras/pull/9112
    '''
    if is_GPU:
        return Bidirectional(CuDNNGRU(units=n_units,
                                      return_sequences=True),
                             merge_mode='concat', weights=None)(my_seq)
    else:
        return Bidirectional(GRU(units=n_units,
                                 activation='tanh',
                                 dropout=0.0,
                                 recurrent_dropout=0.0,
                                 implementation=1,
                                 return_sequences=True,
                                 reset_after=True,
                                 recurrent_activation='sigmoid'),
                             merge_mode='concat', weights=None)(my_seq)

# = = = = = = = = = = = = = = =

docs = np.load(path_to_data + 'documents.npy')

with open(path_to_data + 'train_idxs.txt', 'r') as file:
    train_idxs = file.read().splitlines()

with open(path_to_data + 'test_idxs.txt', 'r') as file:
    test_idxs = file.read().splitlines()

train_idxs = [int(elt) for elt in train_idxs]
test_idxs = [int(elt) for elt in test_idxs]

docs_test = docs[test_idxs,:,:]

# = = = = = TRAINING RESULTS = = = = =

for tgt in range(3,4):

    if tgt == 3 :
        embeddings = np.load(path_to_data + 'new_embeddings.npy')
    else :
        embeddings = np.load(path_to_data + 'embeddings.npy')
        embeddings[:,5] = embeddings[:,5]/np.linalg.norm(embeddings[:,5])
        embeddings[:,6] = embeddings[:,6]/np.linalg.norm(embeddings[:,6])

    print('* * * * * * *',tgt,'* * * * * * *')

    with open(path_to_data + '/model_history_' + str(tgt) + '.json', 'r') as file:
        hist = json.load(file)

    val_mse = hist['val_loss']
    val_mae = hist['val_mean_absolute_error']

    min_val_mse = min(val_mse)
    min_val_mae = min(val_mae)

    best_epoch = val_mse.index(min_val_mse) + 1

    print('best epoch:',best_epoch)
    print('best val MSE',round(min_val_mse,3))
    print('best val MAE',round(min_val_mae,3))

# = = = = = PREDICTIONS = = = = =

all_preds_mean = []
all_preds_han = []

for tgt in range(4):

    print('* * * * * * *',tgt,'* * * * * * *')

    # * * * mean baseline * * *

    with open(path_to_data + 'targets/train/target_' + str(tgt) + '.txt', 'r') as file:
        target = file.read().splitlines()

    target = np.array(target).astype('float')
    target_mean = np.mean(target)
    all_preds_mean.append([target_mean]*len(test_idxs))

    # * * * HAN * * *

    # = = = = = hyper-parameters = = = = =

    # relevant hyper-parameters
    n_context_vect = 1
    n_units = 32
    n_dense = 0
    drop_rate = 0 # prediction mode
    rnn = 'lstm'
    method = 'linear'
    n_rnn = 1

    if method == 'sigmoid' :
        min = np.min(target_train)
        max = np.max(target_train)
        d = np.abs(max - min)
        target_train = (target_train + abs(min))/d

    sent_ints = Input(shape=(docs_test.shape[2],))

    sent_wv = Embedding(input_dim=embeddings.shape[0],
                        output_dim=embeddings.shape[1],
                        weights=[embeddings],
                        input_length=docs_test.shape[2],
                        trainable=False,
                        )(sent_ints)

    sent_wv_dr = Dropout(drop_rate)(sent_wv)
    sent_wa = sent_wv_dr
    if rnn == 'gru' :
        for k in range(n_rnn) :
            sent_wa = bidir_gru(sent_wa,n_units,is_GPU)
    if rnn == 'lstm' :
        for k in range(n_rnn) :
            sent_wa = bidir_lstm(sent_wa,n_units,is_GPU)
    sent_att_vec,word_att_coeffs = AttentionWithContext(n_context_vect = n_context_vect, return_coefficients=True)(sent_wa)
    sent_att_vec_dr = Dropout(drop_rate)(sent_att_vec)
    sent_encoder = Model(sent_ints,sent_att_vec_dr)
    sent_encoder.summary()

    doc_ints = Input(shape=(docs_test.shape[1],docs_test.shape[2],))
    sent_att_vecs_dr = TimeDistributed(sent_encoder)(doc_ints)
    doc_sa = sent_att_vecs_dr
    if rnn == 'gru' :
        for k in range(n_rnn) :
            doc_sa = bidir_gru(doc_sa,n_units,is_GPU)
    if rnn == 'lstm' :
        for k in range(n_rnn) :
            doc_sa = bidir_lstm(doc_sa,n_units,is_GPU)
    doc_att_vec,sent_att_coeffs = AttentionWithContext(n_context_vect = n_context_vect, return_coefficients=True)(doc_sa)
    doc_att_vec_dr = Dropout(drop_rate)(doc_att_vec)

    #doc_att_vec_dr = BatchNormalization()(doc_att_vec_dr)

    for k in range(n_dense) :
         doc_att_vec_dr = Dense(units = int(n_units/2.), activation='relu')(doc_att_vec_dr)
         doc_att_vec_dr = Dropout(0.2)(doc_att_vec_dr)

    #doc_att_vec_dr = BatchNormalization()(doc_att_vec_dr)

    if method == 'sigmoid' :
        preds = Dense(units=1, activation='sigmoid')(doc_att_vec_dr)
        preds = Lambda(lambda x: x*d - abs(min))(preds)
    else :
        doc_att_vec_dr = Dense(units = int(n_units/2.), activation='relu')(doc_att_vec_dr)
        preds = Dense(units=1, activation='linear')(doc_att_vec_dr)

    model = Model(doc_ints,preds)
    model.summary()

    model.load_weights(path_to_data + 'model_' + str(tgt))

    all_preds_han.append(model.predict(docs_test).tolist())

# flatten
all_preds_mean = [elt for sublist in all_preds_mean for elt in sublist]
all_preds_han = [elt[0] for sublist in all_preds_han for elt in sublist]

# write predictions in Kaggle format
with open(path_to_data + 'predictions_mean.txt', 'w') as file:
    file.write('id,pred\n')
    for idx,pred in enumerate(all_preds_mean):
        pred = format(pred, '.7f')
        file.write(str(idx) + ',' + pred + '\n')

with open(path_to_data + 'predictions_han.txt', 'w') as file:
    file.write('id,pred\n')
    for idx,pred in enumerate(all_preds_han):
        pred = format(pred, '.7f')
        file.write(str(idx) + ',' + pred + '\n')
