__author__ = 'hadyelsahar'

from IPython.core.debugger import Tracer; debug_here = Tracer()

from sklearn.base import BaseEstimator, ClassifierMixin
import tensorflow as tf

class CNN_DISTMULT(BaseEstimator, ClassifierMixin):
    """
    CNN_DISTMULT is a CNN encoder
    """

    @staticmethod
    def weight_variable(shape):
        """
        To create this model, we need to create a lot of weights and biases.
        One should generally initialize weights with a small amount of noise for symmetry breaking,
        and to prevent 0 gradients. Since we're using ReLU neurons,
        it is also good practice to initialize them with a slightly positive initial bias to avoid "dead neurons.
        " Instead of doing this repeatedly while we build the model,
        let's create two handy functions to do it for us.
        :param shape:
        :return:
        """
        initial = tf.truncated_normal(shape, stddev=0.1)
        return tf.Variable(initial, validate_shape=True)

    @staticmethod
    def bias_variable(shape):
        initial = tf.constant(0.1, shape=shape)
        return tf.Variable(initial, validate_shape=True)

    @staticmethod
    def conv2d(x, W):
        # by choosing [1,1,1,1] and "same" the output dimension == input dimension
        return tf.nn.conv2d(x, W, strides=[1, 1, 1, 1], padding='VALID')

    @staticmethod
    def max_pool_2x2(x):
        return tf.nn.max_pool(x, ksize=[1, 2, 2, 1],
                              strides=[1, 2, 2, 1], padding='SAME')


    def __init__(self, input_shape, embedding_shape, conv_shape, negative_sample= 100, epochs=2500, batchsize=50, dropout=0.5):
        """
        :param input_shape: [m,n,c] length width and feature maps the input to the encoder (technically c = 1)
        :param embedding_shape : [ne,le] number of entities in KB, length of embedding vectors of entities and relations
        :param conv_shape: width and height of the convolution mask to be chosen
        :param negative_sample: the number of entities to be chosen as a negative sample
        :param epochs:
        :param batchsize:
        :param dropout:
        :return:
        """

        self.m, self.n, self.c = input_shape
        self.ne, self.le = embedding_shape
        self.conv_width, self.conv_length = conv_shape
        self.negative_sample = negative_sample
        self.epochs = epochs
        self.batchsize = batchsize
        self.dropout = dropout
        self.best_acc = 0

        ##################
        # Network Inputs #
        ##################


        # inputs to the networks in each training sample:
        # word vector representation of the input sentence
        # 4 dimensional input : datasize x seqwidth x veclength x channels
        self.x = tf.placeholder(tf.float32,  [self.batchsize, self.m, self.n, self.c], name="X")

        # id of the correct entity subject that exists in the sentence
        self.es_id = tf.placeholder(tf.int64, [self.batchsize], name="es")
        # id of the correct entity object that exists in the sentence
        self.eo_id = tf.placeholder(tf.int64, [self.batchsize], name="eo")

        # id of the correct entity subject that exists in the sentence
        self.es_ns = tf.placeholder(tf.int64, [self.batchsize, self.negative_sample], name="es_ns")
        # id of the correct entity object that exists in the sentence
        self.eo_ns = tf.placeholder(tf.int64, [self.batchsize, self.negative_sample], name="eo_ns")


        ##########################
        # Entity Representations #
        ##########################

        # Vector representations of each entity to be learned during training
        self.Ent = CNN_DISTMULT.weight_variable([self.ne, self.le])

        ####################
        # CNN Architecture #
        ####################
        # First Layer convolution #

        # convolution mask weights to be learned
        d1, d2, d3, d4 = [self.conv_width, self.conv_length, self.c, 1]
        #  d1, d2 : convolution filter size
        #  d3 : the number of input channels
        #  d4 : the number of output channels  = 1
        W_conv1 = CNN_DISTMULT.weight_variable([d1, d2, d3, d4])
        b_conv1 = CNN_DISTMULT.bias_variable([d4])

        h_conv1 = tf.nn.relu(CNN_DISTMULT.conv2d(self.x, W_conv1) + b_conv1, name="convolution")  # output of the convolution layer same dimensions as X     1000 X Sent Width X 200 X 1
        # debug_here()
        h_conv1 = tf.squeeze(h_conv1, [3])                                                        # drop the unneeded channel layer (knowing it's = 1 )
        h_pool1 = tf.reduce_max(h_conv1, 1, keep_dims=True, name="Maxpool")                       # apply max pooling to all vector coming out from the convolution layer. 1000 X 1 X 200

        # Automatically calculate the size of the output of the first convolution layer

        self.keep_prob = tf.placeholder("float")
        r_drop = tf.nn.dropout(h_pool1, self.keep_prob, name="dropout")                             # 1000 X 1 X 200

        self.r = r_drop                                                                             # 1000 X 1 X 200

        es = tf.gather(self.Ent, self.es_id,name="es-gather")    # 1000 X 1 X 200
        eo = tf.gather(self.Ent, self.eo_id, name="eo-gather")    # 1000 X 1 X 200

        es_corrupt = tf.gather(self.Ent, self.es_ns, name="es-corrupt-gather")    # 1000 X 20 X 200
        eo_corrupt = tf.gather(self.Ent, self.eo_ns, name="eo-corrupt-gather")    # 1000 X 20 X 200

        # debug_here()
        self.r = tf.reshape(self.r, [self.batchsize, 1, self.le])
        es = tf.reshape(es, [self.batchsize, 1, self.le])
        eo = tf.reshape(eo, [self.batchsize, 1, self.le])
        es_corrupt = tf.reshape(es_corrupt, [self.batchsize, self.negative_sample, self.le])
        eo_corrupt = tf.reshape(eo_corrupt, [self.batchsize, self.negative_sample, self.le])
        # calculating score correct  dimension # 1000 X 1
        # es * eo  =>  1000 X 1 X 200
        # r        =>  1000 X 1 X 200
        # r  * ( es * eo ) => 1000 X 1 X 200
        # Sum over

        # debug_here()
        self.r = tf.nn.l2_normalize(self.r, 1)
        score_correct = tf.reduce_sum(self.r * (es * eo), 2)                     # 1000 X 1
        score_corrupt_sub = tf.reduce_sum(self.r * (es_corrupt * eo), 2)     # 1000 X 20
        score_corrupt_obj = tf.reduce_sum(self.r * (es * eo_corrupt), 2)     # 1000 X 20

        score_corrupt = tf.concat(1, [score_corrupt_sub, score_corrupt_obj])        # 1000 X 40
        # score_corrupt = score_corrupt_obj
        # debug_here()
        self.loss_function = tf.cast(tf.reduce_sum(tf.nn.relu(score_corrupt - score_correct + 1)), "float")

        # self.train_step = tf.train.AdamOptimizer().minimize(self.loss_function)
        self.train_step = tf.train.AdamOptimizer().minimize(self.loss_function)

        # Normalize Vectors :
        self.Ent = tf.nn.l2_normalize(self.Ent, 1)

        self.sess = tf.InteractiveSession(config=tf.ConfigProto(allow_soft_placement=True))
        self.sess.run(tf.initialize_all_variables())


    def fit(self, batch):
        """
        :param :
                    d : the size of the training data
                    m : number of inputs  layer0 (+ padding)
                    n : size of each vector representation of each input to layer 0
                    c : number of input channels  1

        :param es_id: list of entities ids as subjects
        :param eo_id: list of entities ids as objects
        :param es_ns: list of negative sample entities ids as subjects
        :param eo_ns: list of negative sample entities ids as objects

        :return: trained CNN Class = self
        """

        self.m = batch[0].shape[1]
        self.n = batch[0].shape[2]

        # if i % 100 == 0:
        #
        #     train_accuracy = self.loss_function.eval(feed_dict={self.x: batch[0],
        #                                                         self.es_id: batch[1],
        #                                                         self.eo_id: batch[2],
        #                                                         self.es_ns: batch[3],
        #                                                         self.eo_ns: batch[4], self.keep_prob:1.0})
        #     print("step %d, loss function %g" % (i, train_accuracy))

        self.train_step.run(feed_dict={self.x: batch[0],
                                       self.es_id: batch[1],
                                       self.eo_id: batch[2],
                                       self.es_ns: batch[3],
                                       self.eo_ns: batch[4],  self.keep_prob: self.dropout})

        return self

    def encode(self, X):
        return self.r.eval(feed_dict={self.x: X, self.keep_prob: 1.0})

    def savemodel(self, filename):
        saver = tf.train.Saver()
        save_path = saver.save(self.sess, filename)
        print("Model saved in file: %s" % save_path)

    def loadmodel(self, filename):
        saver = tf.train.Saver()
        saver.restore(self.sess, filename)
        print("Model restored.")

    def device_for_node(n):
        if n.type == "MatMul":
            return "/gpu:0"
        else:
            return "/cpu:0"

