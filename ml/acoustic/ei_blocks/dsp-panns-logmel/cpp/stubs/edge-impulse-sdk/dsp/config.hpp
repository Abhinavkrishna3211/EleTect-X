#ifndef STUB_EI_DSP_CONFIG_HPP
#define STUB_EI_DSP_CONFIG_HPP
// numpy_types.h includes this unconditionally to pick up the SDK's compile
// time switches. Only two reach the declarations this block depends on.

// 0 selects the std::function form of signal_t::get_data; 1 selects a raw
// function pointer. panns_logmel.cpp calls it the same way under either, so
// this check is not sensitive to the project's real setting - but it is the
// SDK default, so it is what gets exercised here.
#define EIDSP_SIGNAL_C_FN_POINTER 0

// Off, so numpy_types.h does not pull in the allocation-tracking header.
#define EIDSP_TRACK_ALLOCATIONS 0
#endif
