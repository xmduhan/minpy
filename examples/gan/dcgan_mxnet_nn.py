from data_utils import get_mnist
import argparse
from mxnet.context import Context

from time import time
import numpy as np
import mxnet as mx
import mxnet.contrib.autograd as _autograd
from mxnet.io import NDArrayIter

# input shape
gnet_input_size = (100,1, 1)
nc = 3
ndf = 64
ngf = 64
dnet_input_size=(3, 64, 64)
batch_size = 64
Z = 100
lr = 0.0002
beta1 = 0.5
use_bias = False
fix_gamma = True
eps = 1e-5 + 1e-12

class GenerativeNet(nn.Layer):
    def __init__(self, ngf, nc, no_bias):
        super(GenerativeNet, self).__init__()
        self.layers = nn.Sequential()
        _deconvolution_bn_relu(ngf * 8, kernel_size=4, use_bias=use_bias, in_filters=1)
        _deconvolution_bn_relu(ngf * 4, kernel_size=4, stride=2, pad=1, use_bias=use_bias, in_filters=ngf*8)
        _deconvolution_bn_relu(nn.Deconv(ngf * 2, kernel_size=4, stride=2, pad=1, use_bias=use_bias, in_filters=ngf*4)
        _deconvolution_bn_relu(nn.Deconv(ngf, kernel_size=4, stride=2, pad=1, use_bias=use_bias, in_filters=ngf*2)
        _deconvolution_bn_relu(nn.Deconv(nc, kernel_size=4, stride=2, pad=1, use_bias=use_bias, in_filters=ngf)
        self.layers.add(Tanh())

    @staticmethod
    def _deconvolution_bn_relu(**kwargs):
        defaults = {'kernel' : (3, 3), 'no_bias' : True}
        defaults.update(kwargs)
        self.layers.add(nn.Deconv(**defaults))
        self.layers.add(nn.BatchNorm(fix_gamma=False))
        self.layers.add(ReLU())

    def generic_forward(self, data):
        data = data
        output = self.layers(data)
        return output
    
    def loss(self, data, labels):
        return mx.nd.sum(mx.nd.dot(data, labels))


class DiscriminativeNet(Model):
    def __init__(self, ndf, no_bias):
        super(DiscriminativeNet, self).__init__()
        self.layers = Sequential(
                self._convolution_leaky(kernel=(4,4), stride=(2,2), pad=(1,1), num_filter=ndf, no_bias=no_bias),
                self._convolution_bn_leaky(kernel=(4,4), stride=(2,2), pad=(1,1), num_filter=ndf*2, no_bias=no_bias),
                self._convolution_bn_leaky(kernel=(4,4), stride=(2,2), pad=(1,1), num_filter=ndf*4, no_bias=no_bias),
                self._convolution_bn_leaky(kernel=(4,4), stride=(2,2), pad=(1,1), num_filter=ndf*8, no_bias=no_bias),
                Convolution(kernel=(4,4), num_filter=1, no_bias=no_bias),
                Flatten(),
        )

    @staticmethod
    def _convolution_bn_leaky(**kwargs):
        defaults = {'kernel' : (3, 3), 'stride' : (1, 1), 'pad' : (1, 1), 'no_bias' : True}
        defaults.update(kwargs)
        leaky_defaults = {'slope': 0.2}
        return Sequential(
            Convolution(**defaults),
            BatchNorm(fix_gamma=False),
            LeakyReLU(**leaky_defaults),
        )

    @staticmethod
    def _convolution_leaky(**kwargs):
        defaults = {'kernel' : (3, 3), 'stride' : (1, 1), 'pad' : (1, 1), 'no_bias' : True}
        defaults.update(kwargs)
        leaky_defaults = {'slope': 0.2}
        return Sequential(
            Convolution(**defaults),
            LeakyReLU(**leaky_defaults),
        )

    @Model.decorator
    def forward(self, data):
        output = self.layers(data)
        return output

    @Model.decorator
    def loss(self, data, labels):
        return mx.nd.LogisticRegressionOutput(data, labels)

class RandIter(mx.io.DataIter):
    def __init__(self, batch_size, ndim):
        self.batch_size = batch_size
        self.ndim = ndim
        self.provide_data = [('rand', (batch_size, ndim, 1, 1))]
        self.provide_label = [np.zeros(batch_size)]

    def iter_next(self):
        return True

    def getdata(self):
        return [mx.nd.normal(0, 1.0, shape=(self.batch_size, self.ndim, 1, 1)).copyto(Context.default_ctx)]

def main():
    # Create model.
    gnet_model = GenerativeNet(ngf, nc, no_bias)
    dnet_model = DiscriminativeNet(ndf, no_bias)
     
    # Prepare data
    X_train, X_test = get_mnist()
    real_iter = NDArrayIter(X_train, np.ones(X_train.shape[0]), batch_size=batch_size)
    rand_iter = RandIter(batch_size, Z)
    
    gnet_model.params.initialize(mx.init.Xavier(magnitude=2.24), ctx=ctx)
    dnet_model.params.initialize(mx.init.Xavier(magnitude=2.24), ctx=ctx)
    gnet_updater = nn.Optim(gnet_model.params, 'sgd', {'learning_rate':0.1, 'momentum':0.9)
    dnet_updater = nn.Optim(dnet_model.params, 'sgd', {'learning_rate':0.1, 'momentum':0.9)

    # Training    
    epoch_number = 0
    iteration_number = 0
    terminated = False

    while not terminated:
        # training
        epoch_number += 1
        real_iter.reset()
        i = 0 
        for real_batch in real_iter:
            rand_batch = rand_iter.getdata()
            # train real
            dnet_real_output = dnet_model.forward(real_batch.data[0], is_train=True)           
            dnet_real_loss = dnet_model.loss(dnet_real_output, real_batch.label[0], is_train=True)
            _autograd.compute_gradient((dnet_real_loss,))
            dnet_real_grad_dict = dict((grad_key, dnet_model.grad_dict[grad_key].copyto(dnet_model.grad_dict[grad_key].context)) for grad_key in dnet_model.grad_dict.keys())

            # train fake, by default, bp will not pass to the input of dnet
            generated_data = gnet_model.forward(rand_batch[0], is_train=True)
            dnet_fake_output = dnet_model.forward(generated_data.detach(), is_train=True)
            dnet_fake_loss = dnet_model.loss(dnet_fake_output, mx.nd.zeros(generated_data.shape[0]), is_train=True)
            _autograd.compute_gradient((dnet_fake_loss,))

            # update dnet
            for each_key in dnet_real_grad_dict:
                dnet_model.grad_dict[each_key] += dnet_real_grad_dict[each_key]
            dnet_updater(dnet_model.grad_dict)

            # ff dnet using fake data and real label
            dnet_fake_output = dnet_model.forward(generated_data, is_train=True)
            dnet_loss_to_train_gnet = dnet_model.loss(dnet_fake_output, mx.nd.ones(generated_data.shape[0]), is_train=True)
            _autograd.compute_gradient((dnet_loss_to_train_gnet,))
            gnet_updater(gnet_model.grad_dict)
            print ('to train gnet')
            print (dnet_loss_to_train_gnet.asnumpy())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Deep Convolutional Generative Adversarial Net")
    parser.add_argument('--gpu_index', type=int, default=1)
    args = parser.parse_args()
    context = mx.cpu() if args.gpu_index < 0 else mx.gpu(args.gpu_index)
    Context.default_ctx = context
    main()
