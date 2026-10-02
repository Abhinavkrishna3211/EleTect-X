#ifndef STUB_EI_VECTOR_H
#define STUB_EI_VECTOR_H
// The SDK's allocator-aware vector. Only ei_matrix's convenience
// constructor mentions it, and this block never calls that constructor.
#include <vector>
template <typename T>
using ei_vector = std::vector<T>;
#endif
