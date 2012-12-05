from . import util, element, numpy, _

# CHECKS

def check_localgradient( localgradient ):
  def localgradient_wrapper( func, ndims ):
    lgrad = localgradient( func, ndims )
    assert lgrad.ndim == func.ndim + 1 \
       and all( sh2 in (sh1,1) for sh1, sh2 in zip( func.shape + (ndims,), lgrad.shape ) ), \
        'bug found in localgradient: %s -> %s' % ( func.shape, lgrad.shape )
    return lgrad
  return localgradient_wrapper

def combined_shape( *shapes ):
  'determine shape after singleton expansion'

  ndim = len(shapes[0])
  combshape = [1] * ndim
  for shape in shapes:
    assert len(shape) == ndim
    for i, sh in enumerate(shape):
      if combshape[i] == 1:
        combshape[i] = sh
      else:
        assert sh in ( combshape[i], 1 )
  return tuple(combshape)

# END CHECKS

def isiterable( obj ):
  try:
    iter(obj)
  except TypeError:
    return False
  return True

def obj2str( obj ):
  'convert object to string'

  if isinstance( obj, numpy.ndarray ):
    if obj.size < 4:
      return str(obj.tolist()).replace(' ','')
    return 'array<%s>' % 'x'.join( map( str, obj.shape ) )
  if isinstance( obj, list ):
    return '[#%d]' % len(obj)
  if isinstance( obj, (tuple,set) ):
    if len(obj) < 4:
      return '(%s)' % ','.join( obj2str(o) for o in obj )
    return '(#%d)' % len(obj)
  if isinstance( obj, dict ):
    return '{#%d}@%x' % ( len(obj), id(obj) )
  if isinstance( obj, DofAxis ):
    return '$'
  if isinstance( obj, slice ):
    I = ''
    if obj.start is not None:
      I += str(obj.start)
    I += ':'
    if obj.stop is not None:
      I += str(obj.stop)
    if obj.step is not None:
      I += ':' + str(obj.step)
    return I
  if obj is Ellipsis:
    return '...'
  if obj is None:
    return '_'
  if obj is POINTS:
    return '<points>'
  if obj is ELEM:
    return '<elem>'
  return str(obj)

class StaticArray( numpy.ndarray ):
  'array wrapper'

  def __new__( cls, array ):
    'new'

    return numpy.asarray( array ).view( cls )

  def __eq__( self, other ):
    'compare'

    if self is other:
      return True
    if self.ndim == 0 and isinstance(other,(int,float)):
      return self.view(numpy.ndarray) == other
    if not isinstance( other, numpy.ndarray ) or self.shape != other.shape:
      return False
    return ( self.view(numpy.ndarray) == other.view(numpy.ndarray) ).all()

  def __ne__( self, other ):
    'not equal'

    return not self == other

  def __nonzero__( self ):
    'nonzero'

    return bool( ( self.view( numpy.ndarray ) != 0 ).any() )

  def reciprocal( self ):
    'reciprocal'

    return StaticArray( numpy.reciprocal(self) )

  def expand( self, shape ):
    'expand'

    shape = tuple(shape)
    assert len(shape) == self.ndim
    if shape == self.shape:
      return self

    return Expand( self, shape )

  def align( self, axes, ndim ):
    'align'

    assert self.ndim == len(axes)
    assert all( 0 <= ax < ndim for ax in axes )
    trans = numpy.argsort( axes )
    sortaxes = numpy.take( axes, trans )
    assert numpy.all( sortaxes[1:] != sortaxes[:-1] ), 'duplicate axes in %s' % axes
    item = [ _ ] * ndim
    for ax, sh in zip( axes, self.shape ):
      item[ax] = slice(None)
    return self.transpose( trans )[ tuple(item) ]

  def get( self, i, item ):
    'get item'

    assert isinstance(item,int)
    s = [ slice(None) ] * self.ndim
    s[i] = item if self.shape[i] > 1 else 0
    return StaticArray( self[tuple(s)] )

  def insert( self, axes ):
    'insert newaxis'

    axes = normdim( self.ndim+len(axes), axes )
    if not axes:
      return self
    s = [slice(None)] * self.ndim
    for ax in axes:
      s.insert( ax, _ )
    return self[ tuple(s) ]

  def indices( self ):
    'get indices for numpy array'

    return ()

  def grad( self, coords ):
    'local derivative'

    return ZERO( self.shape + coords.shape )

  def sum( self, axes=-1 ):
    'sum over multiply axes'

    arr = self.view( numpy.ndarray )
    for ax in reversed( normdim( self.ndim, axes if isiterable(axes) else [axes] ) ):
      arr = arr.sum( ax )
    return StaticArray( arr )

  def det( self, *axes ):
    'determinant'

    return util.det( self, *axes )

  def inv( self, *axes ):
    'determinant'

    return util.inv( self, axes )

  def norm2( self, axis=-1 ):
    'norm2'

    return util.norm2( self, axis )

  def takediag( self, ax1, ax2 ):
    'takediag'

    return util.takediag( self, ax1, ax2 )

  @check_localgradient
  def localgradient( self, ndims ):
    'local derivative'

    return ZERO( self.shape + (ndims,) )

  def concatenate( self, other, axis ):
    'concatenate'

    return StaticArray( numpy.concatenate( [self,other], axis ) )

ZERO = lambda shape: StaticArray(0).reshape([1]*len(shape)).expand(shape)

graphviz_warn = { 'fontcolor': 'white', 'fillcolor': 'black', 'style': 'filled' }

def normdim( length, n ):
  'sort and make positive'

  normed = []
  for ni in n:
    if ni < 0:
      ni += length
    assert 0 <= ni < length, 'out of range: 0 < %d >= %d' % ( ni, length )
    normed.append( ni )
  normed.sort()
  return normed

# EVALUABLE

class Evaluable( object ):
  'evaluable base classs'

  operations = None

  def __init__( self, args, evalf ):
    'constructor'

    self.__args = tuple(args)
    self.__evalf = evalf

  def recurse_index( self, data, operations ):
    'compile'

    indices = numpy.empty( len(self.__args), dtype=int )
    for iarg, arg in enumerate( self.__args ):
      if isinstance(arg,Evaluable):
        for idx, (op,idcs) in enumerate( operations ):
          if op == arg:
            break
        else:
          idx = arg.recurse_index(data,operations)
      elif arg is ELEM:
        idx = -2
      elif arg is POINTS:
        idx = -1
      else:
        data.insert( 0, arg )
        idx = -len(data)-2
      indices[iarg] = idx
    operations.append( (self,indices) )
    return len(operations)-1

  def compile( self ):
    'compile'

    if self.operations is None:
      self.data = []
      self.operations = []
      self.recurse_index( self.data, self.operations ) # compile expressions

  def __call__( self, elem, points ):
    'evaluate'

    self.compile()
    if isinstance( points, str ):
      points = elem.eval(points)

    N = len(self.data) + 2

    values = list( self.data )
    values.append( elem )
    values.append( points )
    for op, indices in self.operations:
      args = [ values[N+i] for i in indices ]
      try:
        retval = op.__evalf( *args )
      except:
        self.printstack( values )
        raise
      values.append( retval )
    return values[-1]

  def __graphviz__( self ):
    'graphviz representation'

    import inspect
    try:
      argnames, varargs, keywords, defaults = inspect.getargspec( self.__evalf )
    except:
      argnames = [ '%%%d' % n for n in range(len(self.__args)) ]
    else:
      for n in range( len(self.__args) - len(argnames) ):
        argnames.append( '%s[%d]' % ( varargs or '*', n ) )
    args = [ '%s=%s' % ( argname, obj2str(arg) ) for argname, arg in zip( argnames, self.__args ) if not isinstance(arg,Evaluable) ]
    label = self.__class__.__name__
    return { 'label': r'\n'.join( [ label ] + args ) }

  def graphviz( self, values=None ):
    'create function graph'

    import os, subprocess

    DOT = '/usr/bin/dot'
    if not os.path.isfile( DOT ) or not os.access( DOT, os.X_OK ):
      return False

    self.compile()
    if values is None:
      values = self.data + [ '<elem>', '<points>' ]

    N = len(self.data) + 2
    dofaxes = {} # labels for dofaxes

    imgpath = util.getpath( 'dot{0:03x}.jpg' )
    dot = subprocess.Popen( [DOT,'-Tjpg'], stdin=subprocess.PIPE, stdout=open(imgpath,'w') )

    print >> dot.stdin, 'digraph {'
    print >> dot.stdin, 'graph [ dpi=72 ];'

    for i, (op,indices) in enumerate( self.operations ):

      try:
        code = op.__evalf.func_code
        argnames = code.co_varnames[ :min(code.co_argcount,len(indices)) ]
      except:
        argnames = ()
      argnames += tuple( '%%%d' % n for n in range( len(indices) - len(argnames) ) )

      node = op.__graphviz__()
      node['label'] = '%d. %s' % ( i, node.get('label','') )
      print >> dot.stdin, '%d [%s]' % ( i, ' '.join( '%s="%s"' % item for item in node.iteritems() ) )

      for n, idx in enumerate( indices ):
        if idx >= 0:
          print >> dot.stdin, '%d -> %d [label="%s"];' % ( idx, i, argnames[n] );

    print >> dot.stdin, '}'
    dot.stdin.close()

    return os.path.basename( imgpath )

  def printstack( self, values=None ):
    'print stack'

    self.compile()
    if values is None:
      values = self.data + ( '<elem>', '<points>' )

    N = len(self.data) + 2

    print 'call stack:'
    for i, (op,indices) in enumerate( self.operations ):
      args = [ '%%%d' % idx if idx >= 0 else obj2str(values[N+idx]) for idx in indices ]
      try:
        code = op.__evalf.func_code
        names = code.co_varnames[ :code.co_argcount ]
        names += tuple( '%s[%d]' % ( code.co_varnames[ code.co_argcount ], n ) for n in range( len(indices) - len(names) ) )
        args = [ '%s=%s' % item for item in zip( names, args ) ]
      except:
        pass
      objstr = '%s( %s )' % ( op.__evalf.__name__, ', '.join( args ) )
      if N+i < len(values):
        objstr += ' = %s %s' % ( obj2str(values[N+i]), type(values[N+i]) )
      elif N+i == len(values):
        objstr += ' <-----ERROR'
      print '%2d: %s' % ( i, objstr )

  def __eq__( self, other ):
    'compare'

    return self is other or ( isinstance(other,Evaluable) and self.__evalf is other.__evalf and self.__args == other.__args )

  def __str__( self ):
    'string representation'

    key = str(self.__class__.__name__)
    lines = []
    indent = '\n' + ' ' + ' ' * len(key)
    for it in reversed( self.__args ):
      lines.append( indent.join( obj2str(it).splitlines() ) )
      indent = '\n' + '|' + ' ' * len(key)
    indent = '\n' + '+' + '-' * (len(key)-1) + ' '
    return key + ' ' + indent.join( reversed( lines ) )

ELEM = object()
POINTS = object()

class Tuple( Evaluable ):
  'combine'

  def __init__( self, items ):
    'constructor'

    self.items = tuple(items)
    Evaluable.__init__( self, args=items, evalf=self.vartuple )

  def __iter__( self ):
    'iterate'

    return iter(self.items)

  def __len__( self ):
    'length'

    return len(self.items)

  def __getitem__( self, item ):
    'get item'

    return self.items[item]

  def __add__( self, other ):
    'add'

    return Tuple( self.items + tuple(other) )

  def __radd__( self, other ):
    'add'

    return Tuple( tuple(other) + self.items )

  @staticmethod
  def vartuple( *f ):
    'evaluate'

    return f

def Zip( *args ):
  'zip items together'

  args = map( tuple, args )
  n = len( args[0] )
  assert all( len(arg) == n for arg in args[1:] ), 'zipping items of different length'
  return Tuple( [ Tuple(v) for v in zip( *args ) ] )

def merge( func0, *funcs ): # temporary
  'merge disjoint function spaces into one'

  assert func0.__class__ is Function
  shape = func0.shape
  mapping = func0.mapping.copy()
  nelems = len( func0.mapping )
  isfuncsp = shape and isinstance( shape[0], DofAxis )
  if isfuncsp:
    dofmap = shape[0].mapping.copy()
    ndofs = int(shape[0])
    shape = shape[1:]
  for func in funcs:
    assert func.__class__ is Function
    if func.shape and isinstance( func.shape[0], DofAxis ):
      assert isfuncsp and func.shape[1:] == shape
      dofmap.update( (elem,idx+ndofs) for (elem,idx) in func.shape[0].mapping.iteritems() )
      ndofs += int(func.shape[0])
    else:
      assert not isfuncsp and func.shape == shape
    mapping.update( func.mapping )
    nelems += len( func.mapping )
  assert nelems == len( mapping ), 'duplicate elements'
  if isfuncsp:
    shape = ( DofAxis(ndofs,dofmap), ) + shape
  return Function( shape, mapping )

# ARRAY FUNCTIONS

class ArrayFunc( Evaluable ):
  'array function'

  __array_priority__ = 1. # fix numpy's idiotic default behaviour

  mul_priority = 0
  add_priority = 0

  def __init__( self, evalf, args, shape ):
    'constructor'

    self.evalf = evalf
    self.shape = tuple(shape)
    self.ndim = len(self.shape)
    Evaluable.__init__( self, evalf=evalf, args=args )

  def __getitem__( self, item ):
    'get item'
  
    tmp = item
    item = list( item if isinstance( item, tuple ) else [item] )
    n = 0
    arr = self
    while item:
      it = item.pop(0)
      if isinstance(it,int):
        arr = arr.get(n,it)
      elif it == _:
        arr = arr.align( [ i+(i>=n) for i in range(arr.ndim) ], arr.ndim+1 )
        n += 1
      elif it == slice(None):
        n += 1
      elif it == Ellipsis:
        remaining_items = len(item) - item.count(_)
        skip = arr.ndim - n - remaining_items
        assert skip >= 0
        n += skip
      elif isinstance(it,slice) and it.step in (1,None) and it.stop == it.start + 1:
        arr = arr.get(n,it.start).insert([n])
        n += 1
      else:
        raise NotImplementedError
      assert n <= arr.ndim
    return arr

  def reciprocal( self ):
    'reciprocal'

    return Reciprocal( self )

  def expand( self, shape ):
    'expand'

    shape = tuple(shape)
    assert len(shape) == self.ndim
    if shape == self.shape:
      return self

    return Expand( self, shape )

  def get( self, i, item ):
    'get item'

    shape = list(self.shape)
    sh = shape.pop(i)
    assert isinstance(sh,int), 'cannot get item %r from axis %r' % ( item, sh )
    item, = normdim( sh, [item] )
    return Get( self, (i,item) )

  def align( self, axes, ndim ):
    'insert singleton dimension'

    assert all( 0 <= ax < ndim for ax in axes )
    if list(axes) == range(ndim):
      return self
    return Align( self, axes, ndim )

  def __iter__( self ):
    'split first axis'

    if not self.shape:
      raise TypeError, 'scalar function is not iterable'

    return ( self[i,...] for i in range(self.shape[0]) )

  def find( self, elem, target, start, tol=1e-10, maxiter=999 ):
    'iteratively find x for f(x) = target, starting at x=start'

    points = start
    Jinv = self.localgradient( elem.ndims ).inv(0,1)
    r = target - self( elem, points )
    niter = 0
    while numpy.any( util.contract( r, r, axis=-1 ) > tol ):
      niter += 1
      if niter >= maxiter:
        raise Exception, 'failed to converge in %d iterations' % maxiter
      points = points.offset( util.contract( Jinv( elem, points ), r[:,_,:], axis=-1 ) )
      r = target - self( elem, points )
    return points

  def chain( self, func ):
    'chain function spaces together'
    
    n1 = int(func.shape[0])
    n2 = n1 + int(self.shape[0])
    return OffsetWrapper( self, offset=n1, ndofs=n2 )

  def sum( self, axes=-1 ):
    'sum'

    axes = normdim( self.ndim, axes if isiterable(axes) else [axes] )
    if not axes:
      return self

    func = self
    for ax in reversed( axes ):
      assert self.shape[ax] == 1
      func = func.get( ax, 0 )
    return func

    #return Sum( self, axes )

  def normalized( self, axis=-1 ):
    'normalize dimension'

    reshape = [ slice(None) ] * len(self.shape)
    reshape[axis] = _
    return self / self.norm2( axis )[ tuple(reshape) ]

  def normal( self, ndims=-1 ):
    'normal'

    assert len(self.shape) == 1
    if ndims <= 0:
      ndims += self.shape[0]

    if self.shape[0] == 2 and ndims == 1:
      grad = self.localgradient( ndims=1 )
      normal = Concatenate([ grad[1,:], -grad[0,:] ])
    elif self.shape[0] == 3 and ndims == 2:
      grad = self.localgradient( ndims=2 )
      normal = Cross( grad[:,0], grad[:,1], axis=0 )
    elif self.shape[0] == 2 and ndims == 0:
      grad = self.localgradient( ndims=1 )
      normal = grad[:,0] * Orientation()
    elif self.shape[0] == 3 and ndims == 1:
      grad = self.localgradient( ndims=1 )
      normal = Cross( grad[:,0], self.normal(), axis=0 )
    elif self.shape[0] == 1 and ndims == 0:
      return StaticArray( 1 ) # TODO fix direction!!!!
    else:
      raise NotImplementedError, 'cannot compute normal for %dx%d jacobian' % ( self.shape[0], ndims )
    return normal.normalized(0)

  def iweights( self, ndims ):
    'integration weights for [ndims] topology'

    J = self.localgradient( ndims )
    cndims, = self.shape
    assert J.shape == (cndims,ndims), 'wrong jacobian shape: got %s, expected %s' % ( J.shape, (cndims, ndims) )
    if cndims == ndims:
      detJ = J.det( 0, 1 )
    elif ndims == 1:
      detJ = J[:,0].norm2( 0 )
    elif cndims == 3 and ndims == 2:
      detJ = Cross( J[:,0], J[:,1], axis=0 ).norm2( 0 )
    elif ndims == 0:
      detJ = 1
    else:
      raise NotImplementedError, 'cannot compute determinant for %dx%d jacobian' % J.shape[:2]
    return detJ * IWeights()

  def indices( self ):
    'get indices for numpy array'

    return Tuple( sh if isinstance(sh,DofAxis) else slice(None) for sh in self.shape )

  def curvature( self, ndims=-1 ):
    'curvature'

    if ndims <= 0:
      ndims += self.shape[0]
    assert ndims == 1 and self.shape == (2,)
    J = self.localgradient( ndims )
    H = J.localgradient( ndims )
    dx, dy = J[:,0]
    ddx, ddy = H[:,0,0]
    return ( dy * ddx - dx * ddy ) / J[:,0].norm2(0)**3

  def __mod__( self, weights ):
    'dot, new notation'

    return self.dot( weights )

  def dot( self, weights ):
    'dot convenience function'

    weights = StaticArray( weights )
    if not weights:
      return ZERO( weights.shape[1:] + self.shape[1:] )

    # TODO restore:
    #assert int(self.shape[0]) == weights.shape[0]

    func = self[ (slice(None),) + (_,) * (weights.ndim-1) + (slice(None),) * (self.ndim-1) ]
    weights = weights[ (slice(None),) * weights.ndim + (_,) * (self.ndim-1) ]
    assert func.ndim == weights.ndim
    return ( DofIndex( weights, self.shape[0] ) * func ).sum( 0 )

  def inv( self, ax1, ax2 ):
    'inverse'

    return Inverse( self, ax1, ax2 )

  def swapaxes( self, n1, n2 ):
    'swap axes'

    n1, n2 = normdim( self.ndim, (n1,n2) )
    trans = numpy.arange( self.ndim )
    trans[n1] = n2
    trans[n2] = n1
    return self.align( trans, self.ndim )

  def transpose( self, trans ):
    'transpose'

    assert len(trans) == self.ndim
    return self.align( trans, self.ndim )

  def grad( self, coords, ndims=0 ):
    'gradient'

    assert len(coords.shape) == 1
    if ndims <= 0:
      ndims += coords.shape[0]
    J = coords.localgradient( ndims )
    if J.shape[0] == J.shape[1]:
      Jinv = J.inv(0,1)
    elif J.shape[0] == J.shape[1] + 1: # gamma gradient
      Jinv = Concatenate( [ J, coords.normal()[:,_] ], axis=1 ).inv(0,1)[:-1,:]
    else:
      raise Exception, 'cannot invert jacobian'
    return ( self.localgradient( ndims )[...,_] * Jinv ).sum( -2 )

  def symgrad( self, coords, ndims=0 ):
    'gradient'

    g = self.grad( coords, ndims )
    return .5 * ( g + g.swapaxes(-2,-1) )

  def div( self, coords, ndims=0 ):
    'gradient'

    return self.grad( coords, ndims ).trace( -1, -2 )

  def ngrad( self, coords, ndims=0 ):
    'normal gradient'

    return ( self.grad(coords,ndims) * coords.normal(ndims-1) ).sum()

  def nsymgrad( self, coords, ndims=0 ):
    'normal gradient'

    return ( self.symgrad(coords,ndims) * coords.normal(ndims-1) ).sum()

  def norm2( self, axis=-1 ):
    'norm2'

    return ( self * self ).sum( axis )**.5

  def det( self, ax1, ax2 ):
    'determinant'

    if self.shape == ():
      return self

    return Determinant( self, ax1, ax2 )

  def prod( self ):
    'product'

    if self.shape[-1] == 1:
      return self.get( -1, 0 )

    return Product( self )

  def __mul__( self, other ):
    'right multiplication'

    if not isinstance( other, ArrayFunc ):
      other = StaticArray( other )
    elif other.mul_priority > self.mul_priority:
      return other * self # prefer specific over general

    shape, (func1,func2) = util.align_arrays( self, other )

    if not func2:
      return ZERO(shape)

    if not func2 - 1 and func1.shape == shape: # TODO replace mul with repeat if possible
      return func1

    return Multiply( func1, func2 )

  def __rmul__( self, other ):
    'right multiply'

    return self * other

  def __div__( self, other ):
    'divide'
  
    if isinstance( other, ArrayFunc ):
      return Divide( self, other )

    return self * numpy.reciprocal( other ) # faster

  def __rdiv__( self, other ):
    'right divide'

    if not isinstance( other, ArrayFunc ):
      other = StaticArray( other )

    shape, (func1,func2) = util.align_arrays( self, other )

    if not func2:
      return ZERO(shape)
    
    return Divide( func2, func1 )

  def __add__( self, other ):
    'add'

    if not isinstance( other, ArrayFunc ):
      other = StaticArray( other )
    elif other.add_priority > self.add_priority:
      return other + self # prefer specific over general

    shape, (func1,func2) = util.align_arrays( self, other )

    if not other:
      return self

    if self == other:
      return self * 2

    return Add( self, other )

  def __radd__( self, other ):
    'right addition'

    return self + other

  def __sub__( self, other ):
    'subtract'

    if not isinstance( other, ArrayFunc ):
      other = StaticArray( other )
  
    if not other:
      return self

    return Subtract( self, other )

  def __rsub__( self, other ):
    'right subtract'

    if isinstance( other, ArrayFunc ):
      return other - self

    other = StaticArray( other )
    if not other:
      return -self

    return Subtract( other, self )

  def __neg__( self ):
    'negate'

    return Negate( self )

  def __pow__( self, n ):
    'power'

    n = StaticArray(n)
    assert n.ndim == 0

    if n == 0:
      return 1

    if n == 1:
      return self

    return Power( self, n )

  @property
  def T( self ):
    'transpose'

    return self.transpose( range(self.ndim)[::-1] )

  def symmetric( self, n1, n2 ):
    'symmetric'

    return Symmetric( self, n1, n2 )

  def trace( self, n1=-2, n2=-1 ):
    'symmetric'

    return Trace( self, n1, n2 )

  def takediag( self, ax1, ax2 ):
    'takediag'

    ax1, ax2 = normdim( self.ndim, (ax1,ax2) )

#   n1 = self.shape[ax1]
#   n2 = self.shape[ax2]
#   ax = ax1 if n1 == 1 else ax2
#   if self.shape[ax] == 1:
#     return self.get( ax, 0 ) # WRONG

    return TakeDiag( self, ax1, ax2 )

  def concatenate( self, other, axis ):
    'concatenate'

    return Concatenate( [self,other], axis )

  def __graphviz__( self ):
    'graphviz representation'

    prop = Evaluable.__graphviz__( self )
    prop['label'] += r'\n[%s]' % ','.join( '$' if isinstance(ax,DofAxis) else str(ax) for ax in self.shape )
    return prop

class Align( ArrayFunc ):
  'align axes'

  mul_priority = 1
  add_priority = 1

  def __init__( self, func, axes, ndim ):
    'constructor'

    assert func.ndim == len(axes)
    self.func = func
    assert all( 0 <= ax < ndim for ax in axes )
    self.axes = tuple(axes)
    trans = numpy.argsort( axes )
    sortaxes = numpy.take( axes, trans )
    assert numpy.all( sortaxes[1:] != sortaxes[:-1] ), 'duplicate axes in %s' % axes
    if numpy.all( trans == numpy.arange(len(axes)) ):
      trans = None
    shape = [ 1 ] * ndim
    item = [ _ ] * ndim
    for ax, sh in zip( axes, func.shape ):
      shape[ax] = sh
      item[ax] = slice(None)
    item = (Ellipsis,)+tuple(item)
    ArrayFunc.__init__( self, args=[func,trans,item], evalf=self.doalign, shape=shape )

  def align( self, axes, ndim ):
    'align'

    assert len(axes) == self.ndim
    assert all( 0 <= ax < ndim for ax in axes )
    newaxes = [ axes[i] for i in self.axes ]
    return self.func.align( newaxes, ndim )

  def takediag( self, ax1, ax2 ):
    'take diag'

    func = self.func
    ax1, ax2 = normdim( self.ndim, [ax1,ax2] )
    if ax1 not in self.axes and ax2 not in self.axes:
      axes = [ ax - (ax>ax1) - (ax>ax2) for ax in self.axes ]
    elif ax2 not in self.axes:
      axes = [ ax - (ax>ax1) - (ax>ax2) if ax != ax1 else self.ndim-2 for ax in self.axes ]
    elif ax1 not in self.axes:
      axes = [ ax - (ax>ax1) - (ax>ax2) if ax != ax2 else self.ndim-2 for ax in self.axes ]
    else:
      func = func.takediag( self.axes[ax1], self.axes[ax2] )
      axes = [ ax - (ax>ax1) - (ax>ax2) for ax in self.axes if ax not in (ax1,ax2) ] + [ self.ndim-2 ]
    return func.align( axes, self.ndim-1 )

  def get( self, i, item ):
    'get'

    axes = [ ax - (ax>i) for ax in self.axes if ax != i ]
    if len(axes) == len(self.axes):
      return self.func.align( axes, self.ndim-1 )

    n = self.axes.index( i )
    return self.func.get( n, item ).align( axes, self.ndim-1 )

  def sum( self, axes=-1 ):
    'sum'

    axes = normdim( self.ndim, axes if isiterable(axes) else [axes] )
    sumaxes = []
    for ax in axes:
      idx = self.axes.index( ax )
      sumaxes.append( idx )

    trans = [ ax - sum(i<ax for i in axes) for ax in self.axes if ax not in axes ]
    return self.func.sum( sumaxes ).align( trans, self.ndim-len(axes) )

  @staticmethod
  def doalign( arr, trans, item ):
    'align'

    if trans is not None:
      shift = arr.ndim - len(trans)
      trans = range(shift) + [ shift+ax for ax in trans ]
      arr = arr.transpose(trans)
    return arr[ item ]

  def localgradient( self, ndims ):
    'local gradient'

    return self.func.localgradient( ndims ).align( self.axes+(self.ndim,), self.ndim+1 )

  def prepare_binary( self, other ):
    'align binary operand'

    if not isinstance( other, ArrayFunc ):
      other = StaticArray( other )
    shape, (func1,func2) = util.align_arrays( self, other )
    assert isinstance( func1, Align )

    ax1 = func1.axes
    if isinstance( func2, Align ):
      ax2 = func2.axes
      func2 = func2.func
    elif isinstance( func2, StaticArray ):
      ax2 = [ i for i in range(func2.ndim) if func2.shape[i] != 1 ]
      item = [ 0 if func2.shape[i] == 1 else slice(None) for i in range(func1.ndim) ]
      func2 = StaticArray( func2[ tuple(item) ] )
    else:
      return func1, func2, None

    newaxes = set( range(func1.ndim) )
    newaxes.difference_update( ax1 )
    newaxes.difference_update( ax2 )
    if not newaxes:
      return func1, func2, None

    newaxes = sorted( newaxes )
    axes = [ ax for ax in range(func1.ndim) if ax not in newaxes ]
    ax1 = tuple( -numpy.searchsorted( newaxes, ax1 ) + ax1 )
    ax2 = tuple( -numpy.searchsorted( newaxes, ax2 ) + ax2 )
    ndim = func1.ndim - len(newaxes)
    return func1.func.align( ax1, ndim ), func2.align( ax2, ndim ), axes

  def __mul__( self, other ):
    'multiply'

    func1, func2, axes = self.prepare_binary( other )
    return ( func1 * func2 ).align( axes, self.ndim ) if axes is not None \
      else ArrayFunc.__mul__( self, other )

  def __add__( self, other ):
    'multiply'

    func1, func2, axes = self.prepare_binary( other )
    return ( func1 + func2 ).align( axes, self.ndim ) if axes is not None \
      else ArrayFunc.__add__( self, other )

  def __div__( self, other ):
    'multiply'

    func1, func2, axes = self.prepare_binary( other )
    return ( func1 / func2 ).align( axes, self.ndim ) if axes is not None \
      else ArrayFunc.__div__( self, other )

  def __graphviz__( self ):
    'graphviz representation'

    newsh = [ '?' ] * self.ndim
    for src, dst in enumerate( self.axes ):
      newsh[dst] = str(src)
    return { 'shape': 'trapezium',
             'label': ','.join(newsh) }

class Get( ArrayFunc ):
  'get'

  def __init__( self, func, *items ):
    'constructor'

    self.func = func
    self.items = sorted( items, reverse=True )
    s = [ slice(None) ] * func.ndim
    shape = list( func.shape )
    for i, item in self.items:
      s[i] = item
      sh = shape.pop( i )
      assert 0 <= item < sh
    ArrayFunc.__init__( self, args=(func,(Ellipsis,)+tuple(s)), evalf=numpy.ndarray.__getitem__, shape=shape )

  @check_localgradient
  def localgradient( self, ndims ):
    'local gradient'

    f = self.func.localgradient( ndims )
    for i, item in self.items:
      f = f.get( i, item )
    return f

  def get( self, i, item ):
    'get item'

    where, what = zip( *self.items )
    for n, ax in enumerate(where):
      if ax <= i:
        i += 1
      else:
        break
    where = where[:n] + (i,) + where[n:]
    what = what[:n] + (item,) + what[n:]
    items = zip( where, what )
    return Get( self.func, *items )

  def __graphviz__( self ):
    'graphviz representation'

    getitem = [ ':' ] * self.func.ndim
    for src, item in self.items:
      getitem[src] = str(item)
    return { 'shape': 'invtrapezium',
             'label': ','.join(getitem) }

class Reciprocal( ArrayFunc ):
  'reciprocal'

  mul_priority = 5

  def __init__( self, func ):
    'constructor'

    self.func = func
    ArrayFunc.__init__( self, args=[func], evalf=numpy.reciprocal, shape=func.shape )

  def get( self, i, item ):
    'get item'

    return self.func.get( i, item ).reciprocal()

  def align( self, axes, ndim ):
    'align'

    return self.func.align( axes, ndim ).reciprocal()

  def __mul__( self, other ):
    'multiply'

    return other / self.func

class Product( ArrayFunc ):
  'product'

  def __init__( self, func ):
    'constructor'

    ArrayFunc.__init__( self, args=[func,-1], evalf=numpy.prod, shape=func.shape[:-1] )

class OffsetWrapper( ArrayFunc ):
  'chain function spaces'

  def __init__( self, func, offset, ndofs ):
    'constructor'

    self.__dict__.update( func.__dict__ )
    self.func = func
    self.offset = offset
    self.shape = (func.shape[0].transform(ndofs=ndofs,shift=offset),) + func.shape[1:]

  @check_localgradient
  def localgradient( self, ndims ):
    'local gradient'

    return OffsetWrapper( self.func.localgradient( ndims ), offset=self.offset, ndofs=int(self.shape[0]) )

class IWeights( ArrayFunc ):
  'integration weights'

  def __init__( self ):
    'constructor'

    ArrayFunc.__init__( self, args=[POINTS], evalf=self.iweights, shape=() )

  @staticmethod
  def iweights( points ):
    'evaluate'

    return points.weights

class Orientation( ArrayFunc ):
  'point orientation'

  def __init__( self ):
    'constructor'

    ArrayFunc.__init__( self, args=[ELEM], evalf=self.orientation, shape=() )

  @staticmethod
  def orientation( elem ):
    'evaluate'

    # VERY TEMPORARY
    elem, transform = elem.parent
    return ( transform.offset > .5 ) * 2 - 1

class Const( float ): # for select
  def eval( self, points ):
    return numpy.array(self)[...,_]

def const( *args ):
  'select by topology'

  assert len(args)%2 == 0
  mapping = {}
  for topo, val in zip( args[::2], args[1::2] ):
    mapping.update( dict.fromkeys( topo, Const(val) ) )
  return Function( shape=(), mapping=mapping )

class Function( ArrayFunc ):
  'function'

  def __init__( self, dofaxis, stdmap ):
    'constructor'

    self.dofaxis = dofaxis
    self.stdmap = stdmap
    topoelems = set(dofaxis.mapping)
    ArrayFunc.__init__( self, args=[ELEM,POINTS,stdmap,topoelems], evalf=self.hierarchicfunction, shape=[dofaxis] )

  @staticmethod
  def hierarchicfunction( elem, points, stdmap, topoelems ):
    'evaluate'

    ##############################################
    # Cascade until the element is in topoelems  #
    ##############################################

    while elem not in topoelems:
      elem, transform = elem.parent
      points = transform.eval( points )

    ##############################################
    # Assemble all evaluation points             #
    ##############################################

    allfvals = []

    while True:
      
      std = stdmap[elem]
      if std:
        if isinstance( std, tuple ):
          std, keep = std
        else:
          keep = slice(None)
        allfvals.append( std.eval(points)[...,keep] )

      if not elem.parent:
        break

      ############################################
      # Cascade until all levels are covered     #
      ############################################

      elem, transform = elem.parent
      if elem not in stdmap:
        break

      points = transform.eval( points )

    return numpy.concatenate( allfvals, axis=1 )

  def vector( self, ndims ):
    'vectorize'

    return Vectorize( [self]*ndims )

  def localgradient( self, ndims ):
    'local derivative'

    return LocalGradient( self.dofaxis, self.stdmap, ndims, level=1 )

class LocalGradient( ArrayFunc ):
  'local gradient'

  def __init__( self, dofaxis, stdmap, ndims, level ):
    'constructor'

    self.ndims = ndims
    self.dofaxis = dofaxis
    self.stdmap = stdmap
    self.level = level
    topoelems = set(dofaxis.mapping)
    ArrayFunc.__init__( self, args=(ELEM,POINTS,stdmap,topoelems,ndims,level), evalf=self.lgrad, shape=(dofaxis,)+(ndims,)*level )

  def localgradient( self, ndims ):
    'local gradient'

    assert ndims == self.ndims
    return LocalGradient( self.dofaxis, self.stdmap, ndims, self.level+1 )

  @staticmethod
  def lgrad( elem, points, stdmap, topoelems, ndims, level ):
    'evaluate'

    assert elem.ndims <= ndims
    while elem.ndims != ndims:
      elem, transform = elem.parent
      points = transform.eval( points )

    T = 1
    while elem not in topoelems:
      elem, transform = elem.parent
      points = transform.eval( points )
      T = numpy.dot( T, transform.transform )

    allgrads = []
    while True:
      std = stdmap[elem]
      if std:
        if isinstance( std, tuple ):
          std, keep = std
        else:
          keep = slice(None)
        F = std.eval(points,grad=level)[(Ellipsis,keep)+(slice(None),)*level]
        for axis in range( -level, 0 ):
          F = util.transform( F, T, axis=axis )
        allgrads.append( F )
      if not elem.parent:
        break
      elem, transform = elem.parent
      if elem not in stdmap:
        break
      points = transform.eval( points )
      T = numpy.dot( T, transform.transform )

    return numpy.concatenate( allgrads, axis=1 )

class Choose( ArrayFunc ):
  'piecewise function'

  def __init__( self, level, intervals, *funcs ):
    'constructor'

    funcs = tuple( func if isinstance(func,ArrayFunc) else StaticArray(func) for func in funcs )
    shapes = [ f.shape for f in funcs ]
    shape = shapes.pop()
    assert all( sh == shape for sh in shapes )
    assert len(intervals) == len(funcs)-1
    self.level = level
    ArrayFunc.__init__( self, args=(level,intervals)+funcs, evalf=self.choose, shape=level.shape+shape )

  @staticmethod
  def choose( x, intervals, *choices ):
    'evaluate'

    which = 0
    for i in intervals:
      which += ( x > i ).astype( int )
    return numpy.choose( which, choices )

  def localgradient( self, ndims ):
    'gradient'
    #self.funcs = self.choose
    #fun = self.funcs
    grads = [ func.localgradient( ndims ) for func in self.funcs ]
    if not any( grads ): # all-zero special case; better would be allow merging of intervals
      return ZERO( self.shape + (ndims,) )
    return Choose( self.level, self.intervals, *grads )

class Choose2D( ArrayFunc ):
  'piecewise function'

  def __init__( self, coords, contour, fin, fout ):
    'constructor'

    shape, (fin,fout) = util.align_arrays( fin, fout )
    ArrayFunc.__init__( self, args=(coords,contour,fin,fout), evalf=self.choose2d, shape=shape )

  @staticmethod
  def choose2d( xy, contour, fin, fout ):
    'evaluate'

    from matplotlib import nxutils
    mask = nxutils.points_inside_poly( xy.T, contour )
    out = numpy.empty( fin.shape or fout.shape )
    out[...,mask] = fin[...,mask] if fin.shape else fin
    out[...,~mask] = fout[...,~mask] if fout.shape else fout
    return out

class Inverse( ArrayFunc ):
  'inverse'

  def __init__( self, func, ax1, ax2 ):
    'constructor'

    ax1, ax2 = normdim( func.ndim, (ax1,ax2) )
    assert func.shape[ax1] == func.shape[ax2]
    self.func = func
    self.axes = ax1, ax2
    ArrayFunc.__init__( self, args=(func,(ax1-func.ndim,ax2-func.ndim)), evalf=util.inv, shape=func.shape )

  @check_localgradient
  def localgradient( self, ndims ):
    'local gradient'

    ax1, ax2 = self.axes
    G = self.func.localgradient( ndims )
    H = ( self[...,_,_].swapaxes(ax1,-1) * G[...,_].swapaxes(ax2,-1) ).sum()
    I = ( self[...,_,_].swapaxes(ax2,-1) * H[...,_].swapaxes(ax1,-1) ).sum()
    return -I

class TrivialAxis( object ):
  'trivial axis'

  def __init__( self, end, beg=0 ):
    'new'

    self.beg = beg
    self.end = end

  def transform( self, ndofs, shift ):
    'shift numbering and widen axis'

    return TrivialAxis( ndofs, mapping )

  @staticmethod
  def eval( xi, idxmap ):
    'evaluate'

    index = idxmap.get( xi.elem )
    while index is None:
      xi = xi.next
      index = idxmap.get( xi.elem )
    return index

class DofAxis( Evaluable ):
  'dof axis'

  def __init__( self, stop, mapping, start=0 ):
    'new'

    self.start = start
    self.stop = stop
    self.mapping = mapping
    Evaluable.__init__( self, args=(ELEM,mapping), evalf=self.dofaxis )

  def transform( self, ndofs, shift ):
    'shift numbering and widen axis'

    mapping = dict( (elem,idx+shift) for elem, idx in self.mapping.iteritems() )
    return DofAxis( ndofs, mapping )

  @staticmethod
  def dofaxis( elem, idxmap ):
    'evaluate'

    index = idxmap.get( elem )
    while index is None:
      elem, transform = elem.parent
      index = idxmap.get( elem )
    return index

  def __int__( self ):
    'integer'

    return int(self.stop)

  def __eq__( self, other ):
    'equals'

    if self is other:
      return True

    if not isinstance( other, DofAxis ):
      return False
      
    if set(self.mapping) != set(other.mapping):
      return False

    for elem in self.mapping:
      if list(self.mapping[elem]) != list(other.mapping[elem]):
        return False

    return True

  def __add__( self, other ):
    'add'

    if other == 0:
      return self

    assert isinstance( other, DofAxis )

    assert other.start == 0
    mapping = self.mapping.copy()
    ndofs = self.stop - self.start
    for elem, idx2 in other.mapping.iteritems():
      idx1 = mapping.get( elem )
      mapping[ elem ] = idx2 + ndofs if idx1 is None \
                   else numpy.hstack([ idx1, idx2 + ndofs ])
    return DofAxis( start=self.start, stop=self.stop+other.stop, mapping=mapping )

  def __repr__( self ):
    'string representation'

    return 'DofAxis(%d-%d)' % ( self.start, self.stop )

class Concatenate( ArrayFunc ):
  'concatenate'

  mul_priority = 8

  def __init__( self, funcs, axis=0 ):
    'constructor'

    self.funcs = tuple( funcs )
    ndim = funcs[0].ndim
    assert all( func.ndim == ndim for func in funcs[1:] ), 'concatenating functions of unequal dimension'
    shape = numpy.array( funcs[0].shape )
    self.axis, = normdim( ndim, [axis] )
    for func in funcs[1:]:
      assert numpy.all( shape[:self.axis] == func.shape[:self.axis] ) and numpy.all( shape[self.axis+1:] == func.shape[self.axis+1:] ), '%s != %s' % ( shape, func.shape )
      shape[self.axis] += func.shape[self.axis]
    ArrayFunc.__init__( self, args=(self.axis-len(shape),)+self.funcs, evalf=self.concat, shape=shape )

  @staticmethod
  def concat( axis, *arrays ):
    'concatenate, allows for (impl/expl) singleton dims'

    ndim = max( arr.ndim for arr in arrays )
    shape = numpy.zeros( ndim )
    for arr in arrays:
      sh = shape[-arr.ndim:]
      numpy.maximum( sh, arr.shape, out=sh )
    shape[axis] = sum( arr.shape[axis] for arr in arrays )
    concatenated = numpy.empty(shape)
    n0 = 0
    s = [slice(None)]*ndim
    for arr in arrays:
      n1 = n0 + arr.shape[axis]
      s[axis] = slice(n0,n1)
      n0 = n1
      concatenated[tuple(s)] = arr
    assert n1 == shape[axis]
    return concatenated

  def get( self, i, item ):
    'get'

    if i == self.axis:
      assert isinstance( self.shape[i], int )
      for f in self.funcs:
        if item < f.shape[i]:
          return f.get( i, item )
        item -= f.shape[0]

    axis = self.axis - (self.axis > i)
    return Concatenate( [ f.get(i,item) for f in self.funcs ], axis=axis )

  @check_localgradient
  def localgradient( self, ndims ):
    'gradient'

    funcs = [ func.localgradient(ndims) for func in self.funcs ]
    return Concatenate( funcs, axis=self.axis )

  def __mul__( self, other ):
    'multiply'

    if not isinstance( other, Concatenate ) or self.ndim != other.ndim or self.axis != other.axis or [ f.shape[self.axis] for f in self.funcs ] != [ g.shape[other.axis] for g in other.funcs ]:
      return ArrayFunc.__mul__( self, other )

    return Concatenate( [ f * g for f, g in zip(self.funcs,other.funcs) ], self.axis )

  def __add__( self, other ):
    'addition'

    if not isinstance( other, Concatenate ) or self.axis != other.axis:
      return ArrayFunc.__add__( self, other )

    fg = zip( self.funcs, other.funcs )
    if any( f.shape != g.shape for (f,g) in fg ):
      return ArrayFunc.__add__( self, other )

    return Concatenate( [ f+g for (f,g) in fg ], axis=self.axis )

  def sum( self, axes=-1 ):
    'sum'

    axes = normdim( self.ndim, axes if isiterable(axes) else [axes] )
    if self.axis not in axes:
      return ArrayFunc.sum( self, axes )

    axes = [ ax if ax < self.axis else ax-1 for ax in axes if ax != self.axis ]
    return util.sum( f.sum(self.axis) for f in self.funcs ).sum( axes )

  def concatenate( self, other, axis ):
    'concatenate'

    if self.ndim != other.ndim or axis != self.axis:
      ArrayFunc.concatenate( other, axis )

    return Concatenate( self.funcs + (other,), axis )

  def align( self, axes, ndim ):
    'align'

    assert all( 0 <= ax < ndim for ax in axes )
    assert len(axes) == self.ndim
    funcs = [ func.align( axes, ndim ) for func in self.funcs ]
    axis = axes[ self.axis ]
    return Concatenate( funcs, axis )

class Vectorize( ArrayFunc ):
  'vectorize'

  mul_priority = 8

  def __init__( self, funcs ):
    'constructor'

    assert all( f.ndim == funcs[0].ndim for f in funcs[1:] )
    shape = (len(funcs),) + funcs[0].shape[1:] # TODO max over all funcs
    self.funcs = funcs
    shape = ( util.sum( func.shape[0] for func in funcs ), len(funcs) ) + funcs[0].shape[1:]
    ArrayFunc.__init__( self, args=[shape[1:]]+funcs, evalf=self.vectorize, shape=shape )

  def sum( self, axes=-1 ):
    'sum'

    axes = normdim( self.ndim, axes if isiterable(axes) else [axes] )
    if not axes:
      return self

    if axes[0] == 1:
      axes = [ ax-1 for ax in axes[1:] ]
      return Concatenate( self.funcs, axis=0 ).sum( axes )

    if axes[0] > 1:
      axes = [ ax-1 for ax in axes ]
      return Vectorize( [ func.sum(axes) for func in self.funcs ] )

    return ArrayFunc.sum( self, axes )

  def __mul__( self, other ):
    'multiply'

    if not isinstance( other, ArrayFunc ):
      other = StaticArray( other )

    shape, (func1,func2) = util.align_arrays( self, other )

    if not other:
      return ZERO( shape )

    if func1 is not self or func2.shape[0] != 1:
      return ArrayFunc.__mul__( self, other )

    funcs = [ func * func2[:,i if func2.shape[1] > 1 else 0,...] for i, func in enumerate(self.funcs) ]
    return Vectorize( funcs )

  def align( self, axes, ndim ):
    'align'

    if axes[0] != 0 or axes[1] != 1:
      return ArrayFunc.align( self, axes, ndim )

    axes = [ 0 ] + [ ax-1 for ax in axes[2:] ]
    return Vectorize( [ func.align(axes,ndim-1) for func in self.funcs ] )

  @staticmethod
  def vectorize( shape, *funcs ):
    'evaluate'

    axis = -len(shape)
    N = sum( func.shape[axis] for func in funcs )
    data = numpy.zeros( funcs[0].shape[:axis] + (N,) + shape )
    count = 0
    for i, func in enumerate( funcs ):
      n = func.shape[axis]
      ind = ( Ellipsis, slice(count,count+n), i ) + (slice(None),) * (len(shape)-1)
      data[ind] = func
      count += n
    assert count == N
    return data

  @check_localgradient
  def localgradient( self, ndims ):
    'gradient'

    return Vectorize([ func.localgradient(ndims) for func in self.funcs ])

  def trace( self, n1, n2 ):
    'trace'

    n1, n2 = normdim( len(self.shape), (n1,n2) )
    if n1 != 1:
      return ArrayFunc.trace( self, n1, n2 )

    assert self.shape[n2] == len(self.funcs)
    return Concatenate([ func.get(n2-1,idim) for idim, func in enumerate( self.funcs ) ])

  def dot( self, weights ):
    'dot'

#   if all( func == self.funcs[0] for func in self.funcs[1:] ):
#     return self.funcs[0].dot( weights.reshape( len(self.funcs), -1 ).T )

    # TODO broken for merged functions!

    n1 = 0
    conc = None
    for func in self.funcs:
      n0 = n1
      n1 += int(func.shape[0])
      f = func.dot( weights[n0:n1,_] )
      conc = f if conc is None else conc.concatenate( f, axis=0 )
    return conc

class Heaviside( ArrayFunc ):
  'heaviside function'

  def __init__( self, levelset ):
    'constructor'

    self.levelset = levelset
    ArrayFunc.__init__( self, args=[levelset], evalf=self.heaviside, shape=levelset.shape )

  @staticmethod
  def heaviside( f ):
    'evaluate'

    return ( f > 0 ).astype( float )

class UFunc( ArrayFunc ):
  'user function'

  def __init__( self, coords, ufunc, *gradients ):
    'constructor'

    self.coords = coords
    self.gradients = gradients
    ArrayFunc.__init__( self, args=(ufunc,coords), evalf=self.ufunc, shape=ufunc( numpy.zeros( coords.shape ) ).shape )

  @staticmethod
  def ufunc( f, x ):
    'evaluate'

    return f( x )

  @check_localgradient
  def localgradient( self, ndims ):
    'local gradient'

    raise NotImplementedError

  def grad( self, coords, topo ):
    'gradient'

    assert coords is self.coords # TODO check tole of topo arg
    return UFunc( self.coords, *self.gradients )

class Cross( ArrayFunc ):
  'normal'

  def __init__( self, f1, f2, axis ):
    'contructor'

    assert f1.shape == f2.shape
    ArrayFunc.__init__( self, args=(f1,f2,-1,-1,-1,axis-f1.ndim), evalf=numpy.cross, shape=f1.shape )

class Determinant( ArrayFunc ):
  'normal'

  def __init__( self, func, ax1, ax2 ):
    'contructor'

    ax1, ax2 = normdim( len(func.shape), (ax1,ax2) )
    shape = list(func.shape)
    shape.pop(ax2)
    shape.pop(ax1)

    self.axes = ax1, ax2
    self.func = func
    ArrayFunc.__init__( self, args=(func,ax1-func.ndim,ax2-func.ndim), evalf=util.det, shape=shape )

  @check_localgradient
  def localgradient( self, ndims ):
    'local gradient; jacobi formula'

    ax1, ax2 = self.axes
    return self * ( self.func.inv(ax1,ax2).swapaxes(ax1,ax2)[...,_] * self.func.localgradient(ndims) ).sum( [ax1,ax2] )

class DofIndex( ArrayFunc ):
  'element-based indexing'

  def __init__( self, array, dofaxis ):
    'constructor'

    array = array[:int(dofaxis)] # TODO make strict
    shape = (dofaxis,) + array.shape[1:]
    self.array = array
    self.dofaxis = dofaxis
    ArrayFunc.__init__( self, args=(array,dofaxis), evalf=numpy.ndarray.__getitem__, shape=shape )

  def __add__( self, other ):
    'add'

    if not isinstance( other, DofIndex ) or self.dofaxis != other.dofaxis:
      return ArrayFunc.__add__( self, other )

    return DofIndex( self.array + other.array, self.dofaxis )

  def __sub__( self, other ):
    'add'

    if not isinstance( other, DofIndex ) or self.dofaxis != other.dofaxis:
      return ArrayFunc.__sub__( self, other )

    return DofIndex( self.array - other.array, self.dofaxis )

  def concatenate( self, other, axis ):
    'concatenate'

    if axis == 0 or not isinstance( other, DofIndex ) or self.dofaxis != other.dofaxis:
      return ArrayFunc.concatenate( other, axis )

    array = self.array.concatenate( other.array, axis )
    return DofIndex( array, self.dofaxis )

  @check_localgradient
  def localgradient( self, ndims ):
    'local gradient'

    return ZERO( self.shape + (ndims,) )

class Multiply( ArrayFunc ):
  'multiply'

  def __init__( self, func1, func2 ):
    'constructor'

    assert func1.ndim == func2.ndim
    shape = combined_shape( func1.shape, func2.shape )
    self.funcs = func1, func2
    ArrayFunc.__init__( self, args=self.funcs, evalf=numpy.multiply, shape=shape )

  def sum( self, axes=-1 ):
    'sum'

    axes = normdim( self.ndim, axes if isiterable(axes) else [axes] )

    func1, func2 = self.funcs
    dotaxes = []
    shift = 0
    for ax in axes:
      myax = ax - shift
      if func1.shape[myax] == 1 or func2.shape[myax] == 1:
        func1 = func1.sum(ax)
        func2 = func2.sum(ax)
        shift += 1
      else:
        dotaxes.append( myax )
    return Dot( func1, func2, dotaxes ) if dotaxes else func1 * func2

  def get( self, i, item ):
    'get'

    func1, func2 = self.funcs
    return func1.get(i,item) * func2.get(i,item)

  def det( self, ax1, ax2 ):
    'determinant'

    if self.funcs[0].shape == ():
      return self.funcs[1].det( ax1, ax2 ) * self.funcs[0]

    if self.funcs[1].shape == ():
      return self.funcs[0].det( ax1, ax2 ) * self.funcs[1]

    return ArrayFunc.det( self, ax1, ax2 )

  def prod( self ):
    'product'

    func1, func2 = self.funcs
    n = self.shape[-1]
    return ( func1.get(-1,0)**n if func1.shape[-1] == 1 else func1.prod() ) \
         * ( func2.get(-1,0)**n if func2.shape[-1] == 1 else func2.prod() )

  @check_localgradient
  def localgradient( self, ndims ):
    'gradient'

    func1, func2 = self.funcs
    return func1[...,_] * func2.localgradient(ndims) \
         + func2[...,_] * func1.localgradient(ndims)

class Divide( ArrayFunc ):
  'divide'

  def __init__( self, func1, func2 ):
    'constructor'

    if not isinstance( func1, ArrayFunc ):
      func1 = StaticArray( func1 )
    if not isinstance( func2, ArrayFunc ):
      func2 = StaticArray( func2 )

    shape, self.funcs = util.align_arrays( func1, func2 )
    ArrayFunc.__init__( self, args=self.funcs, evalf=numpy.divide, shape=shape )

  def get( self, i, item ):
    'get item'

    func1, func2 = self.funcs
    return func1.get(i,item) / func2.get(i,item)

  @check_localgradient
  def localgradient( self, ndims ):
    'local gradient'

    func1, func2 = self.funcs
    grad1 = func1.localgradient(ndims)
    grad2 = func2.localgradient(ndims) 
    return ( grad1 - func1[...,_] * grad2 / func2[...,_] ) / func2[...,_]

class Negate( ArrayFunc ):
  'negate'

  mul_priority = 10

  def __init__( self, func ):
    'constructor'

    self.func = func
    ArrayFunc.__init__( self, args=[func], evalf=numpy.negative, shape=func.shape )

  def __add__( self, other ):
    'addition'

    return other - self.func

  def __sub__( self, other ):

    return -( other + self.func )

  def __mul__( self, other ):
    'multiply'

    if isinstance( other, Negate ):
      return self.func * other.func

    return -( self.func * other )

  def __div__( self, other ):
    'divide'

    if isinstance( other, Negate ):
      return self.func / other.func

    return -( self.func / other )

  def __neg__( self ):
    'negate'

    return self.func

  def align( self, axes, ndim ):
    'align'

    return -self.func.align( axes, ndim )

  def get( self, i, item ):
    'get'

    return -self.func.get( i, item )

  @check_localgradient
  def localgradient( self, ndims ):
    'local gradient'

    return -self.func.localgradient( ndims )

class Add( ArrayFunc ):
  'add'

  def __init__( self, func1, func2 ):
    'constructor'

    shape, self.funcs = util.align_arrays( func1, func2 )
    ArrayFunc.__init__( self, args=self.funcs, evalf=numpy.add, shape=shape )

  @check_localgradient
  def localgradient( self, ndims ):
    'gradient'

    func1, func2 = self.funcs
    return func1.localgradient(ndims) + func2.localgradient(ndims)

  def get( self, i, item ):
    'get'

    func1, func2 = self.funcs
    return func1.get( i, item ) + func2.get( i, item )

class Subtract( ArrayFunc ):
  'subtract'

  def __init__( self, func1, func2 ):
    'constructor'

    shape, self.funcs = util.align_arrays( func1, func2 )
    ArrayFunc.__init__( self, args=self.funcs, evalf=numpy.subtract, shape=shape )

  def __neg__( self ):
    'negate'

    func1, func2 = self.funcs
    return func2 - func1

  @check_localgradient
  def localgradient( self, ndims ):
    'gradient'

    func1, func2 = self.funcs
    return func1.localgradient(ndims) - func2.localgradient(ndims)

class Dot( ArrayFunc ):
  'dot'

  def __init__( self, func1, func2, axes ):
    'constructor'

    shape, (func1,func2) = util.align_arrays( func1, func2 )
    axes = normdim( len(shape), axes )[::-1]
    shape = list(shape)
    for axis in axes:
      shape.pop( axis )

    self.func1 = func1
    self.func2 = func2
    self.axes = axes
    ArrayFunc.__init__( self, args=(func1,func2,tuple( ax-func1.ndim for ax in axes )), evalf=util.contract, shape=shape )

  def get( self, i, item ):
    'get'

    axes = []
    for ax in self.axes:
      if ax <= i:
        i += 1
        axes.append( ax )
      else:
        axes.append( ax-1 )
    return ( self.func1.get(i,item) * self.func2.get(i,item) ).sum( *axes )

  def concatenate( self, other, axis ):
    'concatenate'

    if not isinstance( other, Dot ):
      return ArrayFunc.concatenate( self, other, axis )

    offset = sum( ax <= axis for ax in self.axes )
    if self.func1 == other.func1 and self.func1.shape[axis] == 1:
      return ( self.func1 * self.func2.concatenate( other.func2, axis+offset ) ).sum( self.axes )
    if self.func1 == other.func2 and self.func1.shape[axis] == 1:
      return ( self.func1 * self.func2.concatenate( other.func1, axis+offset ) ).sum( self.axes )
    if self.func2 == other.func1 and self.func2.shape[axis] == 1:
      return ( self.func2 * self.func1.concatenate( other.func2, axis+offset ) ).sum( self.axes )
    if self.func2 == other.func2 and self.func2.shape[axis] == 1:
      return ( self.func2 * self.func1.concatenate( other.func1, axis+offset ) ).sum( self.axes )

    return ArrayFunc.concatenate( self, other, axis )

  @check_localgradient
  def localgradient( self, ndims ):
    'local gradient'

    return ( self.func1.localgradient(ndims) * self.func2[...,_] ).sum( self.axes ) \
         + ( self.func1[...,_] * self.func2.localgradient(ndims) ).sum( self.axes )

class Trace( ArrayFunc ):
  'trace'

  def __init__( self, func, n1, n2 ):
    'constructor'

    n1, n2 = normdim( len(func.shape), (n1,n2) )
    shape = list( func.shape )
    s1 = shape.pop( n2 )
    s2 = shape.pop( n1 )
    assert s1 == s2
    self.func = func
    self.func = func
    self.axes = n1, n2
    ArrayFunc.__init__( self, args=(func,0,n1-func.ndim,n2-func.ndim), evalf=numpy.trace, shape=shape )

  @check_localgradient
  def localgradient( self, ndims ):
    'local gradient'

    grad = self.func.localgradient( ndims )
    return Trace( grad, *self.axes )

class Sum( ArrayFunc ):
  'sum'

  def __init__( self, func, axes ):
    'constructor'

    self.func = func
    self.axes = normdim( func.ndim, axes )
    negaxes = [ ax-func.ndim for ax in reversed(self.axes) ]
    shape = list(func.shape)
    for ax in reversed(self.axes):
      shape.pop(ax)
    ArrayFunc.__init__( self, args=[func,negaxes], evalf=self.dosum, shape=shape )

  @staticmethod
  def dosum( arr, axes ):
    'sum'

    for ax in axes:
      arr = arr.sum(ax)
    return arr

# MATHEMATICAL EXPRESSIONS

class Exp( ArrayFunc ):
  'exponent'

  def __init__( self, func ):
    'constructor'

    assert isinstance( func, ArrayFunc )
    self.func = func
    ArrayFunc.__init__( self, args=[func], evalf=numpy.exp, shape=func.shape )

  @check_localgradient
  def localgradient( self, ndims ):
    'gradient'

    return self * self.func.localgradient(ndims)

class Debug( ArrayFunc ):
  'debug'

  def __init__( self, func, show=False ):
    'constructor'

    self.func = func
    self.show = show
    ArrayFunc.__init__( self, args=[func,show], evalf=self.debug, shape=func.shape )

  @staticmethod
  def debug( arr, show ):
    'debug'

    if show:
      print arr
    return arr

  def localgradient( self, ndims ):
    'local gradient'

    return Debug( self.func.localgradient(ndims) )

  def __str__( self ):
    'string representation'

    return '{DEBUG}'

class Sin( ArrayFunc ):
  'sine'

  def __init__( self, func ):
    'constructor'

    assert isinstance( func, ArrayFunc )
    self.arg = func
    ArrayFunc.__init__( self, args=[func], evalf=numpy.sin, shape=func.shape )

  @check_localgradient
  def localgradient( self, ndims ):
    'gradient'

    return Cos(self.arg) * self.arg.localgradient(ndims)
    
class Cos( ArrayFunc ):
  'cosine'

  def __init__( self, func ):
    'constructor'

    assert isinstance( func, ArrayFunc )
    self.arg = func
    ArrayFunc.__init__( self, args=[func], evalf=numpy.cos, shape=func.shape )

  @check_localgradient
  def localgradient( self, ndims ):
    'gradient'

    return -Sin(self.arg) * self.arg.localgradient(ndims)

class Log( ArrayFunc ):
  'cosine'

  def __init__( self, func ):
    'constructor'

    assert isinstance( func, ArrayFunc )
    self.func = func
    ArrayFunc.__init__( self, args=[func], evalf=numpy.log, shape=func.shape )

  @check_localgradient
  def localgradient( self, ndims ):
    'local gradient'

    return self.func.localgradient(ndims) / self.func

class Arctan2( ArrayFunc ):
  'arctan2'

  def __init__( self, numer, denom ):
    'constructor'

    shape, args = util.align_arrays( numer, denom )
    self.args = numer, denom
    ArrayFunc.__init__( self, args=args, evalf=numpy.arctan2, shape=shape )

  @check_localgradient
  def localgradient( self, ndims ):
    'local gradient'

    y, x = self.args
    return ( x * y.localgradient(ndims) - y * x.localgradient(ndims) ) / ( x**2 + y**2 )

class Power( ArrayFunc ):
  'power'

  def __init__( self, func, power ):
    'constructor'

    assert isinstance( func, ArrayFunc )
    assert isinstance( power, (int,float,numpy.ndarray) )
    self.func = func
    self.power = power
    ArrayFunc.__init__( self, args=[func,power], evalf=numpy.power, shape=func.shape )

  @check_localgradient
  def localgradient( self, ndims ):
    'local gradient'

    return self.power * ( self.func**(self.power-1) )[...,_] * self.func.localgradient(ndims)

  def get( self, i, item ):
    'get'

    return self.func.get( i, item )**self.power

class Min( ArrayFunc ):
  'minimum'

  def __init__( self, func1, func2 ):
    'constructor'

    shape, args = util.align_arrays( func1, func2 )
    ArrayFunc.__init__( self, args=args, evalf=numpy.minimum, shape=shape )

class Max( ArrayFunc ):
  'maximum'

  def __init__( self, func1, func2 ):
    'constructor'

    shape, args = util.align_arrays( func1, func2 )
    ArrayFunc.__init__( self, args=args, evalf=numpy.maximum, shape=shape )

class TakeDiag( ArrayFunc ):
  'extract diagonal'

  def __init__( self, func, ax1, ax2 ):
    'constructor'

    ax1, ax2 = normdim( func.ndim, (ax1,ax2) )
    shape = list( func.shape )
    n = shape.pop(ax2)
    assert n == shape.pop(ax1)
    shape.append( n )
    ArrayFunc.__init__( self, args=[func,ax1-func.ndim,ax2-func.ndim], evalf=util.takediag, shape=shape )

#class Tanh( ArrayFunc ):
#  'hyperbolic tangent'
#
#  eval = staticmethod( numpy.tanh )
#
#  def localgradient( self, ndims ):
#    'gradient'
#
#    return (-Tanh( self.args[0] )**2 + 1.) * self.args[0].localgradient(ndims)

def Tanh( x ):

  return 1 - 2 / ( Exp( 2 * x ) + 1 )

# AUXILIARY OBJECTS

class Diagonalize( ArrayFunc ):
  'diagonal matrix'

  mul_priority = 9

  def __init__( self, func, toaxes ):
    'constructor'

    ax1, ax2 = self.toaxes = normdim( func.ndim+1, toaxes )
    assert ax2 > ax1 # strict
    shape = list( func.shape )
    n = shape.pop()
    shape = shape[:ax1] + [n] + shape[ax1:ax2-1] + [n] + shape[ax2-1:] # shape[ax1] = shape[ax2] = func.shape[-1]
    self.func = func
    ArrayFunc.__init__( self, args=[func,ax1-(func.ndim+1),ax2-(func.ndim+1)], evalf=self.diagonalize, shape=shape )

  @staticmethod
  def diagonalize( data, ax1, ax2 ):
    'evaluate'

    shape = list(data.shape)
    n = shape.pop()
    shape.insert( ax2+len(shape)+1, n )
    shape.insert( ax1+len(shape)+1, n )
    assert shape[ax1] == shape[ax2] == n
    diagonalized = numpy.zeros( shape )
    util.takediag( diagonalized, ax1, ax2 )[:] = data
    return diagonalized

  def get( self, i, item ):
    'get'

    if i in self.toaxes:
      n = self.func.shape[-1]
      stack_axis = self.toaxes[0] if i == self.toaxes[1] else self.toaxes[1]-1
      return Kronecker( self.func.get(-1,item), axis=stack_axis, length=n, pos=item )

    ax1, ax2 = self.toaxes
    if i < ax1:
      ax1 -= 1
      ax2 -= 1
    elif i < ax2:
      ax2 -= 1
      i -= 1
    else:
      i -= 2

    return Diagonalize( self.func.get(i,item), (ax1,ax2) )

  def inv( self, *axes ):
    'inverse'

    if normdim( self.ndim, axes ) == self.toaxes:
      return Diagonalize( self.func.reciprocal(), self.toaxes )

    return ArrayFunc.inv( self, *axes )

  def det( self, *axes ):
    'determinant'

    axes = normdim( self.ndim, axes )
    if axes == self.toaxes:
      return self.func.prod()

    return ArrayFunc.det( self, *axes )

  def __mul__( self, other ):
    'multiply'
 
    if not isinstance( other, ArrayFunc ):
      other = StaticArray( other )

    if not other:
      shape, (func1,func2) = align_arrays( self, other )
      return ZERO( shape )

    toaxes = numpy.array(self.toaxes) - self.ndim
    if other.ndim < self.ndim:
      other = other.align( range(self.ndim-other.ndim,self.ndim), self.ndim )
    return Diagonalize( self.func * other.takediag(*toaxes), toaxes )

  def sum( self, axes=-1 ):
    'sum'

    axes = normdim( self.ndim, axes if isiterable(axes) else [axes] )
    if self.toaxes[0] in axes:
      sumax = self.toaxes[0]
      otherax = self.toaxes[1] - 1
    elif self.toaxes[1] in axes:
      sumax = self.toaxes[1]
      otherax = self.toaxes[0]
    else:
      return ArrayFunc.sum( self, axes )

    trans = range(otherax) + range(otherax+1,self.ndim-1) + [otherax]
    remaining = [ ax if ax < sumax else ax-1 for ax in axes if ax != sumax ]
    return self.func.transpose( trans ).sum( remaining )

  def align( self, axes, ndim ):
    'align'

    assert all( 0 <= ax < ndim for ax in axes )
    assert len(axes) == self.ndim
    ax1, ax2 = self.toaxes
    toaxes = axes[ax1], axes[ax2]
    axes = [ ax - (ax>toaxes[0]) - (ax>toaxes[1]) for ax in axes if ax not in toaxes ] + [ ndim-2 ]
    return Diagonalize( self.func.align( axes, ndim-1 ), toaxes )

  def __graphviz__( self ):
    'graphviz representation'

    prop = ArrayFunc.__graphviz__( self )
    prop.update( graphviz_warn )
    return prop

class Kronecker( ArrayFunc ):
  'kronecker'

  mul_priority = 9

  def __init__( self, func, axis, length, pos ):
    'constructor'

    assert 0 <= pos < length
    self.func = func
    self.axis, = normdim( func.ndim+1, [axis] )
    self.length = length
    self.pos = pos
    shape = list(func.shape)
    shape.insert(axis,length)
    ArrayFunc.__init__( self, args=[func,self.axis-func.ndim,length,pos], evalf=self.kronecker, shape=shape )

  def insert( self, axes ):
    'insert'

    i, = normdim( self.ndim, axes ) # TODO fix for multiple axes
    axis = self.axis
    if i <= self.axis:
      axis += 1
    return Kronecker( self.func.insert([i]), axis, self.length, self.pos )

  def __mul__( self, other ):
    'multiply'

    return Kronecker( self.func * other.get(self.axis,self.pos), self.axis, self.length, self.pos )

  def sum( self, axes=-1 ):
    'sum'

    axes = normdim( self.ndim, axes if isiterable(axes) else [axes] )

    if self.axis not in axes:
      return ArrayFunc.sum( self, axes )

    axes = [ ax if ax <= axes else ax-1 for ax in axes if ax != self.axis ]
    return self.func.sum( axes )

# def align( self, axes, ndim ):
#   'align'

#   assert len(axes) == self.ndim
#   axis = axes[self.axis]
#   trans = [ ax - (ax>self.axis) for ax in axes if ax != self.axis ]
#   print 'ALIGN', axes, self.axis, '->', trans
#   print trans, self.ndim-1
#   print 'ndim', self.ndim
#   return Kronecker( self.func.align(trans,self.ndim-1), axis, self.length, self.pos )

# def __mul__( self, other ):
#   'multiply'

#   shape, (func1,func2) = util.align_arrays( self, other )
#   assert isinstance( func1, Kronecker )
#   return Kronecker( func1.func * func2.get(self.axis,self.pos), self.axis, self.length, self.pos )

  @staticmethod
  def kronecker( func, axis, length, pos ):
    'kronecker'

    shape = list(func.shape)
    axis += len(shape)
    shape.insert(axis,length)
    array = numpy.zeros( shape, dtype=float )
    s = [slice(None)]*array.ndim
    s[axis] = pos
    array[tuple(s)] = func
    return array

  def __graphviz__( self ):
    'graphviz representation'

    prop = ArrayFunc.__graphviz__( self )
    prop.update( graphviz_warn )
    return prop

class Expand( ArrayFunc ):
  'singleton expand'

  mul_priority = 9

  def __init__( self, func, shape ):
    'constructor'

    assert shape
    shape = tuple(shape)
    self.func = func
    assert func.ndim == len(shape)
    for sh1, sh2 in zip( func.shape, shape ):
      assert sh1 in (sh2,1)
    ArrayFunc.__init__( self, args=(func,)+shape, evalf=self.doexpand, shape=shape )

  def __nonzero__( self ):
    'nonzero'

    return self.func.__nonzero__()

  def get( self, i, item ):
    'get'

    i, = normdim( self.ndim, [i] )
    shape = list(self.shape)
    sh = shape.pop(i)
    if sh == 1:
      assert isinstance( sh, int ) and 0 <= item < sh, 'item out of range'
      item = 0
    return self.func.get( i, item ).expand( shape )

  @staticmethod
  def doexpand( arr, *shape ):
    'expand'

    expanded = numpy.empty( arr.shape[:arr.ndim-len(shape)] + tuple( sh if isinstance(sh,int) else len(sh) for sh in shape ) )
    expanded[:] = arr
    return expanded

  def sum( self, axes=-1 ):
    'sum'

    axes = normdim( self.ndim, axes if isiterable(axes) else [axes] )
    func = self.func
    if not func:
      return func.sum( axes )
    factor = 1
    for ax in reversed(axes):
      if func.shape[ax] == 1:
        func = func.get( ax, 0 )
        factor *= self.shape[ax]
      else:
        func = func.sum( [ax] )
    return func * factor

  def prod( self ):
    'prod'

    if self.func.shape[-1] != 1:
      return self.func.prod().expand( self.shape[:-1] )

    return self.func.get( -1, 0 )**self.shape[-1]

  def reciprocal( self ):
    'reciprocal'

    return self.func.reciprocal().expand( self.shape )

  def __add__( self, other ):
    'multiply'

    add = self.func + other
    shape = add.shape[:-self.ndim] + tuple( sh2 if sh1 == 1 else sh1 for sh1, sh2 in zip( add.shape[-self.ndim:], self.shape ) )
    return add.expand( shape )

  def __mul__( self, other ):
    'multiply'

    mul = self.func * other
    shape = mul.shape[:-self.ndim] + tuple( sh2 if sh1 == 1 else sh1 for sh1, sh2 in zip( mul.shape[-self.ndim:], self.shape ) )
    return mul.expand( shape )

  def align( self, axes, ndim ):
    'align'

    shape = [ 1 ] * ndim
    assert all( 0 <= ax < ndim for ax in axes )
    for src, dst in enumerate(axes):
      shape[dst] = self.shape[src]
    return Expand( self.func.align(axes,ndim), shape )

  def __graphviz__( self ):
    'graphviz representation'

    prop = ArrayFunc.__graphviz__( self )
    prop.update( graphviz_warn )
    return prop



# def find( self, x, title=False ):
#   'find physical coordinates in all elements'

#   x = array.asarray( x )
#   assert x.shape[0] == self.topology.ndims
#   ielems = 0
#   coords = []
#   for xi, pi in zip( x, self.gridnodes ):
#     I = numpy.searchsorted( pi, xi )
#     coords.append( ( xi - pi[I-1] ) / ( pi[I] - pi[I-1] ) )
#     ielems = ielems * (len(pi)-1) + (I-1)
#   coords = numpy.array( coords )
#   elems = self.topology.structure.ravel()
#   indices = numpy.arange( len(ielems) )
#   if title:
#     progressbar = util.progressbar( n=indices.size, title=title )
#   while len( ielems ):
#     ielem = ielems[0]
#     select = ( ielems == ielem )
#     elem = elems[ ielem ]
#     xi = elem( coords[:,select] )
#     f = self( xi )
#     f.indices = indices[select]
#     yield f
#     ielems = ielems[~select]
#     coords = coords[:,~select]
#     indices = indices[~select]
#     if title:
#       progressbar.update( progressbar.n-indices.size-1 )

# vim:shiftwidth=2:foldmethod=indent:foldnestmax=2
