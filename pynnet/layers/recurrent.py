from base import *
from simple import SimpleLayer
from pynnet.nlins import *

__all__ = ['RecurrentWrapper']

class RecurrentWrapper(CompositeLayer):
    r"""
    This is a recurrent layer with a one tap delay.  This means it
    gets it own output from the previous step in addition to the
    input provided at each step.
    
    The memory is automatically updated and starts with a zero fill.
    If you want to clear the memory at some point, use the clear()
    function.  It will work on any backend and with any shape.  You
    may have problems on the GPU (and maybe elsewhere) otherwise.
    
    Examples:
    >>> r = RecurrentWrapper(SimpleLayer(2, 3), outshp=(3,))
    >>> r = RecurrentWrapper(LayerStack([SimpleLayer(5,4), SimpleLayer(4,3)]),
    ...                                 outshp=(3,))
    
    NOTE: As is the code should cope with input in more than two
    dimensions, but this is not tested.  If you encounter as bug
    please report it and it will be fixed.

    Also, this layer won't work with layers that have their output
    size proportional to the input size (like ConvLayer).  You can fix
    this by adding a SimpleLayer or similar on top.

    Attributes:
    `base_layer` -- (layer, read-only) the layer upon which this one
                    is based.
    `memory` -- (shared matrix, read-only) Shared memory matrix.
                Overwrite with zeros to clear memory.
    """    
    def __init__(self, layer, outshp,
                 dtype=theano.config.floatX, name=None):
        r"""
        Tests:
        >>> r = RecurrentWrapper(SimpleLayer(10, 5, dtype='float32', name='t'),
        ...                      outshp=(5,), dtype='float32')
        >>> r.memory.value
        array([[ 0.,  0.,  0.,  0.,  0.]], dtype=float32)
        >>> r.get_layer('t')
        t
        >>> r2 = test_saveload(r)
        >>> r2.memory.value
        array([[ 0.,  0.,  0.,  0.,  0.]], dtype=float32)
        >>> r2.get_layer('t')
        t
        """
        self.memory = theano.shared(numpy.zeros((1,)+outshp, dtype=dtype), name='memory')
        self.base_layer = layer
        CompositeLayer.__init__(self, name, layer)

    def clear(self):
        r"""
        Resets the memory to all zeros.
        """
        val = self.memory.value
        val[:] = 0
        self.memory.value = val

    def _save_(self, file):
        val = self.memory.value
        psave((val.shape, val.dtype), file)
        self.base_layer.savef(file)

    def _load1_(self, file):
        shp, dtype = pload(file)
        self.memory = theano.shared(numpy.zeros(shp, dtype=dtype), name='memory')
        self.base_layer = loadf(file)
        self.add(self.base_layer)

    _load_ = _load1_

    def build(self, input, input_shape=None):
        r"""
        Builds the layer with input expresstion `input`.

        Tests:
        >>> r = RecurrentWrapper(SimpleLayer(5, 2, dtype='float32'),
        ...                      outshp=(2,), dtype='float32')
        >>> x = T.fmatrix('x')
        >>> r.build(x, input_shape=(4, 3))
        >>> r.params
        [W, b]
        >>> r.input
        x
        >>> r.output_shape
        (4, 2)
        >>> theano.pp(r.output)
        '<theano.scan.Scan object at ...>(?_steps, x, memory, W, b)[:, 0, :]'
        >>> f = theano.function([x], r.output)
        >>> v = f(numpy.random.random((4, 3)))
        >>> v.dtype
        dtype('float32')
        >>> v.shape
        (4, 2)
        >>> (r.memory.value == v[-1]).all()
        True
        >>> r.build(x)
        >>> r.output_shape
        >>> r=RecurrentWrapper(RecurrentWrapper(SimpleLayer(6,2), (2,)), (2,))
        >>> r.build(x)
        >>> f = theano.function([x], r.output)
        >>> v = f(numpy.random.random((3, 2)))
        >>> v.shape
        (3, 2)
        >>> (r.memory.value == v[-1]).all()
        True
        >>> (r.base_layer.memory.value == v[-1]).all()
        True
        """
        if input_shape is not None:
            inp_shape = (1, input_shape[1]+self.memory.value.shape[1])+input_shape[2:]
        else:
            inp_shape = None

        def f(inp, mem):
            self.base_layer.build(T.join(1, T.unbroadcast(T.shape_padleft(inp),0), mem), inp_shape)
            return self.base_layer.output

        outs, upds = theano.scan(f, sequences=[input], outputs_info=[self.memory])
        
        for s, u in upds.iteritems():
            s.default_update = u
        self.input = input
        if input_shape is None:
            self.output_shape = None
        else:
            self.output_shape = (input_shape[0],)+self.base_layer.output_shape[1:]
        self.output = outs[:,0,:]
        self.params = self.base_layer.params
        self.memory.default_update = outs[-1]