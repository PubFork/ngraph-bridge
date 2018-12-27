import tensorflow as tf, numpy as np
from tensorflow.core.framework import graph_pb2
from google.protobuf import text_format
import pdb, os
import gzip, shutil
from mnist import MNIST
try:
    from urllib.request import urlretrieve
except ImportError:
    from urllib import urlretrieve  # py2
try:
    from urllib.parse import urljoin
except ImportError:
    from urlparse import urljoin
import pickle as pkl


import ngraph_bridge


# https://github.com/datapythonista/mnist/blob/master/mnist/__init__.py
def download_file(fname, target_dir, force=False):
    if not os.path.exists(target_dir):
      os.mkdir(target_dir)
  
    target_fname = os.path.join(target_dir, fname)

    if force or not os.path.isfile(target_fname):
        url = urljoin('http://yann.lecun.com/exdb/mnist/', fname)
        urlretrieve(url, target_fname)

    unzip_name = target_fname[:-3]
    with gzip.open(target_fname, 'rb') as f_in:
      with open(unzip_name, 'wb') as f_out:
          shutil.copyfileobj(f_in, f_out)

    return unzip_name

def get_whole_dataset(mnist_dir):
  dl_fl_names = ['t10k-images-idx3-ubyte.gz', 't10k-labels-idx1-ubyte.gz', 'train-images-idx3-ubyte.gz', 'train-labels-idx1-ubyte.gz']
  print ([download_file(item, mnist_dir) for item in dl_fl_names])


def read_graphdef(graph_file=None):
    graphdef = graph_pb2.GraphDef()
    if graph_file is None:
        graph_file="/nfs/site/home/sarkars/nishant_tf_sandbox/dump/final_int8_mnist.pbtxt"
        #graph_file = "final_int8_mnist_dequant_scaled.pbtxt"
    f = open(graph_file, "r")
    text_format.Merge(f.read(), graphdef)

    for node in graphdef.node:
        print(node.name)
        print("  " + node.op)
        print("  inputs:")
        for input in node.input:
            print("    " + input)
    return graphdef

def test1():  #quantize.
    graphdef = read_graphdef()

    mnist_dir = './mnist'
    get_whole_dataset(mnist_dir)  # create mnist_dir and download data in here

    mndata = MNIST(mnist_dir)
    images, labels = mndata.load_testing()
    #ngraph_bridge.disable()

    tensornames = [
        "import/pool1/MaxPool_eightbit_quantize_conv1/Relu:0",
        "import/pool1/MaxPool_eightbit_quantize_conv1/Relu:1",
        "import/pool1/MaxPool_eightbit_quantize_conv1/Relu:2",
        "import/pool1/MaxPool_eightbit_quantized:0",
        "import/pool1/MaxPool_eightbit_quantized:1",
        "import/pool1/MaxPool_eightbit_quantized:2",
        "import/conv2/Conv2D_eightbit_requantize:0",  #quack-bark
        "import/conv2/Conv2D_eightbit_requantize:1",
        "import/conv2/Conv2D_eightbit_requantize:2",
        "import/accuracy:0",
        "import/fc2/MatMul:0",  # X
        "import/fc1/MatMul:0",   # X
        "import/pool2/MaxPool_eightbit_quantized:0",    #diff by 1
        "import/pool2/MaxPool:0"   # XXX: dequant after second QMP
        #"import/conv1/Relu:0"
    ]
    #pool1/MaxPool_eightbit_quantized
    bs = 1
    with tf.Session() as sess:
        graph = tf.import_graph_def(graphdef)
        #placeholders = [ op for op in tf.get_default_graph().get_operations() if op.type == "Placeholder"]
        intensor1 = tf.get_default_graph().get_tensor_by_name('import/Placeholder:0')
        intensor2 = tf.get_default_graph().get_tensor_by_name('import/Placeholder_1:0')
        #print placeholders
        #pool1/MaxPool_eightbit_quantized  QMP
        #pool1/MaxPool_eightbit_quantize_conv1/Relu  Qv2
        #import/accuracy
        #conv1/Relu
        #conv2/Conv2D_eightbit_requantize  custom op
        outtensors = [tf.get_default_graph().get_tensor_by_name(tname) for tname in tensornames]
        #print [ op for op in tf.get_default_graph().get_operations() if op.type == "QuantizeV2"]

        outvals = sess.run(outtensors, feed_dict = {intensor1 : np.array(images[0:bs]), intensor2 : np.array(labels[0:bs])})

    print ('===============')
    ngraph_bridge.disable()

    with tf.Session() as sess:
        graph = tf.import_graph_def(graphdef)
        intensor1 = tf.get_default_graph().get_tensor_by_name('import/Placeholder:0')
        intensor2 = tf.get_default_graph().get_tensor_by_name('import/Placeholder_1:0')
        outtensors = [tf.get_default_graph().get_tensor_by_name(tname) for tname in tensornames]
        outvals_tf = sess.run(outtensors, feed_dict = {intensor1 : np.array(images[0:bs]), intensor2 : np.array(labels[0:bs])})

    for t1, t2, tname in zip(outvals, outvals_tf, tensornames):
        print(tname, np.linalg.norm(t1.astype('float') - t2.astype('float')))
        print(tname, t1.shape)
    pdb.set_trace()
    print('hello')


def test2():  #dequant
    graphdef = read_graphdef()

    mnist_dir = './mnist'
    get_whole_dataset(mnist_dir)  # create mnist_dir and download data in here

    mndata = MNIST(mnist_dir)
    images, labels = mndata.load_testing()

    tensornames = ['import/pool2/MaxPool:0']

    datain = np.random.randint(500, size=[16,7,7,64]).astype('uint8')
    ngraph_bridge.enable()
    with tf.Session() as sess:
        graph = tf.import_graph_def(graphdef)
        intensor1 = tf.get_default_graph().get_tensor_by_name('import/pool2/MaxPool_eightbit_quantized:0')
        intensor2 = tf.get_default_graph().get_tensor_by_name('import/pool2/MaxPool_eightbit_quantized:1')
        intensor3 = tf.get_default_graph().get_tensor_by_name('import/pool2/MaxPool_eightbit_quantized:2')
        #deq?
        outtensors = [tf.get_default_graph().get_tensor_by_name(tname) for tname in tensornames]
        
        outvals = sess.run(outtensors, feed_dict = {intensor1 : datain, intensor2 : np.array(0).astype('float'), intensor3 : np.array(511).astype('float')})

    print ('===============')
    ngraph_bridge.disable()
    with tf.Session() as sess:
        graph = tf.import_graph_def(graphdef)
        intensor1 = tf.get_default_graph().get_tensor_by_name('import/pool2/MaxPool_eightbit_quantized:0')
        intensor2 = tf.get_default_graph().get_tensor_by_name('import/pool2/MaxPool_eightbit_quantized:1')
        intensor3 = tf.get_default_graph().get_tensor_by_name('import/pool2/MaxPool_eightbit_quantized:2')
        outtensors = [tf.get_default_graph().get_tensor_by_name(tname) for tname in tensornames]
        outvals_tf = sess.run(outtensors, feed_dict = {intensor1 : datain, intensor2 : np.array(0).astype('float'), intensor3 : np.array(511).astype('float')})

    for t1, t2 in zip(outvals, outvals_tf):
        print(np.linalg.norm(t1.astype('float') - t2.astype('float')))
        print(t1.shape)
    print('hello')


def test3():
    graphdef = read_graphdef()

    tensornames = [
        'import/conv2/Conv2D_eightbit_requantize:0',
    ]
    bs = 1
    ngraph_bridge.enable()
    with tf.Session() as sess:
        graph = tf.import_graph_def(graphdef)
        intensor1 = tf.get_default_graph().get_tensor_by_name('import/pool1/MaxPool_eightbit_quantized:0')
        intensor2 = tf.get_default_graph().get_tensor_by_name('import/pool1/MaxPool_eightbit_quantized:1')
        intensor3 = tf.get_default_graph().get_tensor_by_name('import/pool1/MaxPool_eightbit_quantized:2')
        intensor4 = tf.get_default_graph().get_tensor_by_name("import/conv2/Variable_qint8_const:0")
        outtensors = [tf.get_default_graph().get_tensor_by_name(tname) for tname in tensornames]
        outvals = sess.run(outtensors, feed_dict = {intensor1 : np.ones([1,14,14,32]).astype('uint8'), intensor2 : np.array(0).astype('float'), intensor3 : np.array(511).astype('float')})

    print ('===============')
    #intensor4 : np.ones([5,5,32,64]).astype('int8')
    ngraph_bridge.disable()
    with tf.Session() as sess:
        graph = tf.import_graph_def(graphdef)
        intensor1 = tf.get_default_graph().get_tensor_by_name('import/pool1/MaxPool_eightbit_quantized:0')
        intensor2 = tf.get_default_graph().get_tensor_by_name('import/pool1/MaxPool_eightbit_quantized:1')
        intensor3 = tf.get_default_graph().get_tensor_by_name('import/pool1/MaxPool_eightbit_quantized:2')
        intensor4 = tf.get_default_graph().get_tensor_by_name("import/conv2/Variable_qint8_const:0")
        outtensors = [tf.get_default_graph().get_tensor_by_name(tname) for tname in tensornames]
        outvals_tf = sess.run(outtensors, feed_dict = {intensor1 : np.ones([1,14,14,32]).astype('uint8'), intensor2 : np.array(0).astype('float'), intensor3 : np.array(511).astype('float')})

    for t1, t2 in zip(outvals, outvals_tf):
        print(np.linalg.norm(t1.astype('float') - t2.astype('float')))
        print(t1.shape)
    pdb.set_trace()
    print('hello')


def test_acc():
    graphdef = read_graphdef()

    mnist_dir = './mnist'
    get_whole_dataset(mnist_dir)  # create mnist_dir and download data in here

    mndata = MNIST(mnist_dir)
    images, labels = mndata.load_testing()
    #ngraph_bridge.disable()

    tensornames = [
        "import/accuracy:0",
    ]

    bs = None
    with tf.Session() as sess:
        graph = tf.import_graph_def(graphdef)
        intensor1 = tf.get_default_graph().get_tensor_by_name('import/Placeholder:0')
        intensor2 = tf.get_default_graph().get_tensor_by_name('import/Placeholder_1:0')
        outtensors = [tf.get_default_graph().get_tensor_by_name(tname) for tname in tensornames]
        outvals = sess.run(outtensors, feed_dict = {intensor1 : np.array(images[0:bs]), intensor2 : np.array(labels[0:bs])})
        print (outvals)

    print('disabling ngraph now =====')

    ngraph_bridge.disable()
    with tf.Session() as sess:
        graph = tf.import_graph_def(graphdef)
        intensor1 = tf.get_default_graph().get_tensor_by_name('import/Placeholder:0')
        intensor2 = tf.get_default_graph().get_tensor_by_name('import/Placeholder_1:0')
        outtensors = [tf.get_default_graph().get_tensor_by_name(tname) for tname in tensornames]
        outvals = sess.run(outtensors, feed_dict = {intensor1 : np.array(images[0:bs]), intensor2 : np.array(labels[0:bs])})
        print (outvals)
        print(len(images[0:bs]))

from tensorflow.core.framework import graph_pb2
from tensorflow.python.platform import gfile
def load_file(graph_file):
    '''
    can load protobuf (pb or pbtxt). can modify only pbtxt for now
    '''
    if not gfile.Exists(graph_file):
        raise Exception("Input graph file '" + graph_file + "' does not exist!")

    input_binary = graph_file.split('.')[-1] != 'pbtxt'
    graphdef = graph_pb2.GraphDef()
    with open(graph_file, "rb") as f:
        protobuf_str = f.read()
        try:
            if input_binary:
                graphdef.ParseFromString(protobuf_str)
            else:
                text_format.Merge(protobuf_str, graphdef)
        except:
            raise Exception("Failed to read pb or pbtxt. input_binary is " +
                            str(input_binary) + " maybe try flipping it?")
    return graphdef

def test_resnet(datadict=None):  #quantize.
    graphdef = load_file('/nfs/site/home/sarkars/nishant_tf_sandbox/dump/final_int8_resnet50.pb')
    '''
    for node in graphdef.node:
        print(node.name)
        print("  " + node.op)
        #print("  inputs:")
        #for input in node.input:
        #    print("    " + input)
    '''
    tensornames = [
        "import/v0/resnet_v10/conv2/conv2d/Conv2D_eightbit_quantize_v0/mpool0/MaxPool:0",
        "import/v0/resnet_v10/conv2/conv2d/Conv2D_eightbit_quantize_v0/mpool0/MaxPool:1",
        "import/v0/resnet_v10/conv2/conv2d/Conv2D_eightbit_quantize_v0/mpool0/MaxPool:2",

        "import/v0/resnet_v10/conv1/conv2d/Conv2D_eightbit_quantize_v0/mpool0/MaxPool:0",
        "import/v0/resnet_v10/conv1/conv2d/Conv2D_eightbit_quantize_v0/mpool0/MaxPool:1",
        "import/v0/resnet_v10/conv1/conv2d/Conv2D_eightbit_quantize_v0/mpool0/MaxPool:2",

        "import/v0/resnet_v10/conv1/conv2d/Conv2D_eightbit_requantize:0",
        "import/v0/resnet_v10/conv1/conv2d/Conv2D_eightbit_requantize:1",
        "import/v0/resnet_v10/conv1/conv2d/Conv2D_eightbit_requantize:2",

        "import/v0/resnet_v10/conv2/conv2d/Conv2D_eightbit_requantize:0",
        "import/v0/resnet_v10/conv2/conv2d/Conv2D_eightbit_requantize:1",
        "import/v0/resnet_v10/conv2/conv2d/Conv2D_eightbit_requantize:2",

        "import/v0/resnet_v10/conv3/conv2d/Conv2D_eightbit_requantize:0",
        "import/v0/resnet_v10/conv3/conv2d/Conv2D_eightbit_requantize:1",
        "import/v0/resnet_v10/conv3/conv2d/Conv2D_eightbit_requantize:2",


        "import/v0/resnet_v10/conv4/conv2d/Conv2D_eightbit_requantize:0",
        #"import/v0/resnet_v10/conv4/conv2d/Conv2D_eightbit_requantize:1",
        #"import/v0/resnet_v10/conv4/conv2d/Conv2D_eightbit_requantize:2",

        #"import/v0/resnet_v10/conv1/conv2d/kernel_qint8_const:0",
        #"import/v0/resnet_v10/conv1/conv2d/Conv2D_bn_offset:0",
        #"import/v0/resnet_v10/conv1/conv2d/kernel_min:0",
        #"import/v0/resnet_v10/conv1/conv2d/kernel_max:0",
        #"import/v0/resnet_v10/conv1/conv2d/Conv2D_eightbit_requant_range/frozen_min:0",
        #"import/v0/resnet_v10/conv1/conv2d/Conv2D_eightbit_requant_range/frozen_max:0",


       # "import/v0/resnet_v10/conv1/conv2d/kernel_qint8_const:0"
        #"import/v0/resnet_v10/conv2/conv2d/Conv2D_eightbit_requantize:0"
        #"import/v0/resnet_v11/conv7/conv2d/Conv2D_eightbit_requantize:0"
        #"import/predict:0",
    ]
    #pool1/MaxPool_eightbit_quantized
    if datadict is None:
        bs = 1
        indata = np.arange(bs*224*224*3).reshape([bs,224,224,3])%256
    else:
        indata = datadict['import/input:0']
    with tf.Session() as sess:
        graph = tf.import_graph_def(graphdef)
        #placeholders = [ op for op in tf.get_default_graph().get_operations() if op.type == "Placeholder"]
        #import pdb; pdb.set_trace()
        intensor1 = tf.get_default_graph().get_tensor_by_name('import/input:0')
        #intensor2 = tf.get_default_graph().get_tensor_by_name('import/Placeholder_1:0')
        outtensors = [tf.get_default_graph().get_tensor_by_name(tname) for tname in tensornames]
        outvals = sess.run(outtensors, feed_dict = {intensor1 : indata})

    print ('===============')
    ngraph_bridge.disable()

    with tf.Session() as sess:
        graph = tf.import_graph_def(graphdef)
        intensor1 = tf.get_default_graph().get_tensor_by_name('import/input:0')
        outtensors = [tf.get_default_graph().get_tensor_by_name(tname) for tname in tensornames]
        outvals_tf = sess.run(outtensors, feed_dict = {intensor1 : indata})

    for t1, t2, tname in zip(outvals, outvals_tf, tensornames):
        print(tname, np.linalg.norm(t1.astype('float') - t2.astype('float')))
        print(tname, t1.shape)
    if datadict is None:
        datadict = {tname:t1 for t1, tname in zip(outvals_tf, tensornames)}
        datadict['import/input:0'] = indata
        pkl.dump(datadict, open('../datadict.pkl', 'wb'))
    pdb.set_trace()
    print('hello')

'''
def test_resnet_newoponly():
    graphdef = load_file('/localdisk/sarkars/workspace1/cpu_quant/final_int8_resnet50.pb')
    tensornames = ["import/v0/resnet_v10/conv4/conv2d/Conv2D_eightbit_requantize:0"]
    bs = 1
    indata = np.arange(bs*55*55*64).reshape([bs,55, 55, 64])%256
    indata1 = np.arange(bs*55*55*256).reshape([bs,55, 55, 256])%256
    with tf.Session() as sess:
        graph = tf.import_graph_def(graphdef)
        #placeholders = [ op for op in tf.get_default_graph().get_operations() if op.type == "Placeholder"]
        #import pdb; pdb.set_trace()
        intensor1 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v10/conv3/conv2d/Conv2D_eightbit_requantize:0")
        intensor2 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v10/conv3/conv2d/Conv2D_eightbit_requantize:1")
        intensor3 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v10/conv3/conv2d/Conv2D_eightbit_requantize:2")
        intensor4 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v10/conv1/conv2d/Conv2D_eightbit_requantize:0")
        intensor5 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v10/conv1/conv2d/Conv2D_eightbit_requantize:1")
        intensor6 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v10/conv1/conv2d/Conv2D_eightbit_requantize:2")
        #intensor2 = tf.get_default_graph().get_tensor_by_name('import/Placeholder_1:0')
        outtensors = [tf.get_default_graph().get_tensor_by_name(tname) for tname in tensornames]
        outvals = sess.run(outtensors, feed_dict = {intensor1 : indata, intensor2 : -2, intensor3 : 2, intensor4:indata1, intensor5: -1, intensor6:1})
        #pdb.set_trace()
        #print('hello')

    print ('===============')
    ngraph_bridge.disable()

    with tf.Session() as sess:
        graph = tf.import_graph_def(graphdef)
        intensor1 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v10/conv3/conv2d/Conv2D_eightbit_requantize:0")
        intensor2 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v10/conv3/conv2d/Conv2D_eightbit_requantize:1")
        intensor3 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v10/conv3/conv2d/Conv2D_eightbit_requantize:2")
        intensor4 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v10/conv1/conv2d/Conv2D_eightbit_requantize:0")
        intensor5 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v10/conv1/conv2d/Conv2D_eightbit_requantize:1")
        intensor6 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v10/conv1/conv2d/Conv2D_eightbit_requantize:2")
        outtensors = [tf.get_default_graph().get_tensor_by_name(tname) for tname in tensornames]
        outvals_tf = sess.run(outtensors, feed_dict = {intensor1 : indata, intensor2 : -2, intensor3 : 2, intensor4:indata1, intensor5: -1, intensor6:1})

    for t1, t2, tname in zip(outvals, outvals_tf, tensornames):
        print(tname, np.linalg.norm(t1.astype('float') - t2.astype('float')))
        print(tname, t1.shape)
    pdb.set_trace()
    print('hello')


def test_resnet_newunsignedoponly():
    graphdef = load_file('/localdisk/sarkars/workspace1/cpu_quant/final_int8_resnet50.pb')
    tensornames = ["import/v0/resnet_v11/conv7/conv2d/Conv2D_eightbit_requantize:0"]
    bs = 1
    indata = np.arange(bs*55*55*64).reshape([bs,55, 55, 64])%256
    indata1 = np.arange(bs*55*55*256).reshape([bs,55, 55, 256])%256
    with tf.Session() as sess:
        graph = tf.import_graph_def(graphdef)
        #placeholders = [ op for op in tf.get_default_graph().get_operations() if op.type == "Placeholder"]
        #import pdb; pdb.set_trace()
        intensor1 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v11/conv6/conv2d/Conv2D_eightbit_requantize:0")
        intensor2 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v11/conv6/conv2d/Conv2D_eightbit_requantize:1")
        intensor3 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v11/conv6/conv2d/Conv2D_eightbit_requantize:2")
        intensor4 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v10/conv4/conv2d/Conv2D_eightbit_requantize:0")
        intensor5 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v10/conv4/conv2d/Conv2D_eightbit_requantize:1")
        intensor6 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v10/conv4/conv2d/Conv2D_eightbit_requantize:2")
        outtensors = [tf.get_default_graph().get_tensor_by_name(tname) for tname in tensornames]
        outvals = sess.run(outtensors, feed_dict = {intensor1 : indata, intensor2 : -2, intensor3 : 2, intensor4:indata1, intensor5: -1, intensor6:1})
        #pdb.set_trace()
        #print('hello')

    print ('===============')
    ngraph_bridge.disable()

    with tf.Session() as sess:
        graph = tf.import_graph_def(graphdef)
        intensor1 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v11/conv6/conv2d/Conv2D_eightbit_requantize:0")
        intensor2 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v11/conv6/conv2d/Conv2D_eightbit_requantize:1")
        intensor3 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v11/conv6/conv2d/Conv2D_eightbit_requantize:2")
        intensor4 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v10/conv4/conv2d/Conv2D_eightbit_requantize:0")
        intensor5 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v10/conv4/conv2d/Conv2D_eightbit_requantize:1")
        intensor6 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v10/conv4/conv2d/Conv2D_eightbit_requantize:2")
        outtensors = [tf.get_default_graph().get_tensor_by_name(tname) for tname in tensornames]
        outvals_tf = sess.run(outtensors, feed_dict = {intensor1 : indata, intensor2 : -2, intensor3 : 2, intensor4:indata1, intensor5: -1, intensor6:1})

    for t1, t2, tname in zip(outvals, outvals_tf, tensornames):
        print(tname, np.linalg.norm(t1.astype('float') - t2.astype('float')))
        print(tname, t1.shape)
    pdb.set_trace()
    print('hello')


def test_resnet_quackbarkonly():
    graphdef = load_file('/localdisk/sarkars/workspace1/cpu_quant/final_int8_resnet50.pb')
    tensornames = ["import/v0/resnet_v10/conv2/conv2d/Conv2D_eightbit_requantize:0"]
    bs = 1
    indata = np.arange(bs*55*55*64).reshape([bs,55, 55, 64])%256
    #indata1 = np.arange(bs*55*55*256).reshape([bs,55, 55, 256])%256
    with tf.Session() as sess:
        graph = tf.import_graph_def(graphdef)
        #placeholders = [ op for op in tf.get_default_graph().get_operations() if op.type == "Placeholder"]
        #import pdb; pdb.set_trace()
        intensor1 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v10/conv2/conv2d/Conv2D_eightbit_quantize_v0/mpool0/MaxPool:0")
        intensor2 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v10/conv2/conv2d/Conv2D_eightbit_quantize_v0/mpool0/MaxPool:1")
        intensor3 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v10/conv2/conv2d/Conv2D_eightbit_quantize_v0/mpool0/MaxPool:2")
        #intensor3 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v11/conv6/conv2d/Conv2D_eightbit_requantize:2")
        #intensor4 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v10/conv4/conv2d/Conv2D_eightbit_requantize:0")
        #intensor5 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v10/conv4/conv2d/Conv2D_eightbit_requantize:1")
        #intensor6 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v10/conv4/conv2d/Conv2D_eightbit_requantize:2")
        outtensors = [tf.get_default_graph().get_tensor_by_name(tname) for tname in tensornames]
        outvals = sess.run(outtensors, feed_dict = {intensor1 : indata, intensor2 : -2, intensor3 : 2})
        #pdb.set_trace()
        #print('hello')

    print ('===============')
    ngraph_bridge.disable()

    with tf.Session() as sess:
        graph = tf.import_graph_def(graphdef)
        intensor1 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v10/conv2/conv2d/Conv2D_eightbit_quantize_v0/mpool0/MaxPool:0")
        intensor2 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v10/conv2/conv2d/Conv2D_eightbit_quantize_v0/mpool0/MaxPool:1")
        intensor3 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v10/conv2/conv2d/Conv2D_eightbit_quantize_v0/mpool0/MaxPool:2")
        #intensor3 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v11/conv6/conv2d/Conv2D_eightbit_requantize:2")
        #intensor4 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v10/conv4/conv2d/Conv2D_eightbit_requantize:0")
        #intensor5 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v10/conv4/conv2d/Conv2D_eightbit_requantize:1")
        #intensor6 = tf.get_default_graph().get_tensor_by_name("import/v0/resnet_v10/conv4/conv2d/Conv2D_eightbit_requantize:2")
        outtensors = [tf.get_default_graph().get_tensor_by_name(tname) for tname in tensornames]
        outvals_tf = sess.run(outtensors, feed_dict = {intensor1 : indata, intensor2 : -2, intensor3 : 2})

    for t1, t2, tname in zip(outvals, outvals_tf, tensornames):
        print(tname, np.linalg.norm(t1.astype('float') - t2.astype('float')))
        print(tname, t1.shape)
    pdb.set_trace()
    print('hello')
'''

def test_single_node_graph(node_name, inp_tensors_feeddict):
    ngraph_bridge.enable()
    graphdef = load_file('/nfs/site/home/sarkars/nishant_tf_sandbox/dump/final_int8_resnet50.pb')
    tensornames = [node_name]
    bs = 1
    with tf.Session() as sess:
        graph = tf.import_graph_def(graphdef)
        outtensors = [tf.get_default_graph().get_tensor_by_name(tname) for tname in tensornames]
        outvals = sess.run(outtensors, feed_dict = {tf.get_default_graph().get_tensor_by_name(tname):inp_tensors_feeddict[tname] for tname in inp_tensors_feeddict})

    print ('===============')
    ngraph_bridge.disable()

    with tf.Session() as sess:
        graph = tf.import_graph_def(graphdef)
        outtensors = [tf.get_default_graph().get_tensor_by_name(tname) for tname in tensornames]
        outvals_tf = sess.run(outtensors, feed_dict = {tf.get_default_graph().get_tensor_by_name(tname):inp_tensors_feeddict[tname] for tname in inp_tensors_feeddict})

    for t1, t2, tname in zip(outvals, outvals_tf, tensornames):
        print(tname, np.linalg.norm(t1.astype('float') - t2.astype('float')))
        print(tname, t1.shape)
    diff = outvals[0].astype(int) - outvals_tf[0].astype(int)
    print("Max diff val: ", np.max(np.abs(diff)))
    print('Number of non-zero elements in diff: ', np.sum(diff!=0))
    print('Number of zero elements in diff: ', np.sum(diff==0))
    hist = {i:np.sum(diff==i) for i in np.unique(diff)}
    #print(' '.join([str(i) + ':' + str(hist[i]) for i in sorted(hist.keys(), key=lambda x : abs(x))]))
    print('Ending test')

def test_resnet_newoponly_conv4(datadict=None):
    if datadict is None:
        bs = 1
        indata = np.arange(bs*55*55*64).reshape([bs,55, 55, 64])%256
        indata1 = np.arange(bs*55*55*256).reshape([bs,55, 55, 256])%256
        min1 = -2
        min2 = -1
        max1 = 2
        max2 = 1
    else:
        indata = datadict["import/v0/resnet_v10/conv3/conv2d/Conv2D_eightbit_requantize:0"]
        indata1 = datadict["import/v0/resnet_v10/conv1/conv2d/Conv2D_eightbit_requantize:0"]
        min1 = datadict["import/v0/resnet_v10/conv3/conv2d/Conv2D_eightbit_requantize:1"]
        max1 = datadict["import/v0/resnet_v10/conv3/conv2d/Conv2D_eightbit_requantize:2"]
        min2 = datadict["import/v0/resnet_v10/conv1/conv2d/Conv2D_eightbit_requantize:1"]
        max2 = datadict["import/v0/resnet_v10/conv1/conv2d/Conv2D_eightbit_requantize:2"]


    test_single_node_graph('import/v0/resnet_v10/conv4/conv2d/Conv2D_eightbit_requantize:0', {"import/v0/resnet_v10/conv3/conv2d/Conv2D_eightbit_requantize:0": indata,
    "import/v0/resnet_v10/conv3/conv2d/Conv2D_eightbit_requantize:1": min1, 
    "import/v0/resnet_v10/conv3/conv2d/Conv2D_eightbit_requantize:2": max1,
    "import/v0/resnet_v10/conv1/conv2d/Conv2D_eightbit_requantize:0": indata1,
    "import/v0/resnet_v10/conv1/conv2d/Conv2D_eightbit_requantize:1": min2, 
    "import/v0/resnet_v10/conv1/conv2d/Conv2D_eightbit_requantize:2": max2
    })

def test_resnet_newunsignedoponly_conv7(datadict=None):
    if datadict is None:
        bs = 1
        indata = np.arange(bs*55*55*64).reshape([bs,55, 55, 64])%256
        indata1 = np.arange(bs*55*55*256).reshape([bs,55, 55, 256])%256
        min1 = -2
        min2 = -1
        max1 = 2
        max2 = 1
    else:
        indata = datadict["import/v0/resnet_v11/conv6/conv2d/Conv2D_eightbit_requantize:0"]
        indata1 = datadict["import/v0/resnet_v10/conv4/conv2d/Conv2D_eightbit_requantize:0"]
        min1 = datadict["import/v0/resnet_v11/conv6/conv2d/Conv2D_eightbit_requantize:1"]
        max1 = datadict["import/v0/resnet_v11/conv6/conv2d/Conv2D_eightbit_requantize:2"]
        min2 = datadict["import/v0/resnet_v10/conv4/conv2d/Conv2D_eightbit_requantize:1"]
        max2 = datadict["import/v0/resnet_v10/conv4/conv2d/Conv2D_eightbit_requantize:2"]

    test_single_node_graph('import/v0/resnet_v11/conv7/conv2d/Conv2D_eightbit_requantize:0', {"import/v0/resnet_v11/conv6/conv2d/Conv2D_eightbit_requantize:0": indata,
    "import/v0/resnet_v11/conv6/conv2d/Conv2D_eightbit_requantize:1": min1, 
    "import/v0/resnet_v11/conv6/conv2d/Conv2D_eightbit_requantize:2": max1,
    "import/v0/resnet_v10/conv4/conv2d/Conv2D_eightbit_requantize:0": indata1,
    "import/v0/resnet_v10/conv4/conv2d/Conv2D_eightbit_requantize:1": min2, 
    "import/v0/resnet_v10/conv4/conv2d/Conv2D_eightbit_requantize:2": max2
    })

def test_resnet_quackbarkonly_conv2(datadict):
    if datadict is None:
        bs = 1
        indata = np.arange(bs*55*55*64).reshape([bs,55, 55, 64])%256
        mn = -2
        mx = 2
    else:
        indata = datadict["import/v0/resnet_v10/conv2/conv2d/Conv2D_eightbit_quantize_v0/mpool0/MaxPool:0"]
        mn = datadict["import/v0/resnet_v10/conv2/conv2d/Conv2D_eightbit_quantize_v0/mpool0/MaxPool:1"]
        mx = datadict["import/v0/resnet_v10/conv2/conv2d/Conv2D_eightbit_quantize_v0/mpool0/MaxPool:2"]

    test_single_node_graph('import/v0/resnet_v10/conv2/conv2d/Conv2D_eightbit_requantize:0', {"import/v0/resnet_v10/conv2/conv2d/Conv2D_eightbit_quantize_v0/mpool0/MaxPool:0": indata,
    "import/v0/resnet_v10/conv2/conv2d/Conv2D_eightbit_quantize_v0/mpool0/MaxPool:1": mn, 
    "import/v0/resnet_v10/conv2/conv2d/Conv2D_eightbit_quantize_v0/mpool0/MaxPool:2": mx
    })

def test_resnet_quackbarknoreluonly_conv1(datadict):
    if datadict is None:
        bs = 1
        indata = np.arange(bs*55*55*64).reshape([bs,55, 55, 64])%256
        mn = -2
        mx = 2
    else:
        indata = datadict["import/v0/resnet_v10/conv1/conv2d/Conv2D_eightbit_quantize_v0/mpool0/MaxPool:0"]
        mn = datadict["import/v0/resnet_v10/conv1/conv2d/Conv2D_eightbit_quantize_v0/mpool0/MaxPool:1"]
        mx = datadict["import/v0/resnet_v10/conv1/conv2d/Conv2D_eightbit_quantize_v0/mpool0/MaxPool:2"]


    test_single_node_graph('import/v0/resnet_v10/conv1/conv2d/Conv2D_eightbit_requantize:0', {"import/v0/resnet_v10/conv1/conv2d/Conv2D_eightbit_quantize_v0/mpool0/MaxPool:0": indata,
    "import/v0/resnet_v10/conv1/conv2d/Conv2D_eightbit_quantize_v0/mpool0/MaxPool:1": -2, 
    "import/v0/resnet_v10/conv1/conv2d/Conv2D_eightbit_quantize_v0/mpool0/MaxPool:2": 2
    })


def unittest_signedsum():
    def _helper():
        from tensorflow.python.ops import nn_ops
        N = 1
        C = 1
        H = 3
        W = 4
        O = 1
        I = C
        FH = 3
        FW = 3
        input = tf.constant(np.array([1, 2, 3, 4, 5, 6, 7, 0, 1, 2, 3, 4]).reshape([N, H, W, C]), dtype=tf.quint8, name='input')
        filter = tf.constant(np.array([1, 2, 3, 4, 5, 0, 0, 1, 2]).reshape([FH, FW, I, O]), dtype=tf.qint8, name='filter')
        bias = tf.constant(np.array([5]), dtype=tf.qint32, name='bias')
        min_input = 0.0
        max_input = 255.0
        min_filter = -127.0
        max_filter = 127.0
        min_freezed_output = 22.0
        max_freezed_output = 90.0
        summand = tf.constant(np.array([-1, -2, -3, -4, -5, -6, -10, 0, 1, 2, 3, 4]).reshape([N, H, W, C]), dtype=tf.qint8, name='sum')
        min_summand = 22.0
        max_summand = 90.0
        strides = [1,1,1,1]
        padding = "SAME"
        #pdb.set_trace()
        qop = nn_ops.quantized_conv2d_with_bias_signed_sum_and_relu_and_requantize(input, filter, bias, min_input, max_input, min_filter, max_filter, min_freezed_output, max_freezed_output, summand, min_summand, max_summand, strides, padding, out_type=tf.quint8, dilations=[1, 1, 1, 1], name='qop')
        result = tf.Session().run([qop, input, filter, bias, summand])
        for name, val in zip(['qop', 'input', 'filter', 'bias', 'summand'], result):
            print(name, ":", val)

    ngraph_bridge.disable()
    print("Raw TF result")
    _helper()
    print("NGTF result")
    ngraph_bridge.enable()
    _helper()

#test1()
#test_acc()

datadict = pkl.load(open('../datadict.pkl', 'rb'))

test_resnet(datadict)

#test_resnet_newoponly_conv4()
#test_resnet_newunsignedoponly_conv7()
#test_resnet_quackbarkonly_conv2()
#test_resnet_quackbarknoreluonly_conv1()




test_resnet_newoponly_conv4(datadict)
#test_resnet_newunsignedoponly_conv7(datadict)
test_resnet_quackbarkonly_conv2(datadict)
test_resnet_quackbarknoreluonly_conv1(datadict)

#unittest_signedsum()
'''
NGRAPH_TF_LOG_PLACEMENT=1 NGRAPH_PASS_ENABLES="ConstantFolding:1" NGRAPH_TF_DISABLE_DEASSIGN_CLUSTERS=1  python runme_jayram.py
'''
