#ifndef STUB_NUMPY_HPP
#define STUB_NUMPY_HPP
// The real numpy.hpp pulls in the SDK's whole DSP library. This block uses
// none of it - only the types - so the stub forwards to numpy_types.h and
// supplies the allocator macros the porting layer would normally define.
#include <cstdlib>
#define ei_calloc calloc
#define ei_free free
#define ei_malloc malloc
#include "edge-impulse-sdk/dsp/numpy_types.h"
#include "edge-impulse-sdk/dsp/returntypes.hpp"
#endif
