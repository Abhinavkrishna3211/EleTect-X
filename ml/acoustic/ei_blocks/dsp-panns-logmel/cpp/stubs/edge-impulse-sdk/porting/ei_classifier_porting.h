#ifndef STUB_EI_CLASSIFIER_PORTING_H
#define STUB_EI_CLASSIFIER_PORTING_H
// Real signature: int ei_printf(const char *format, ...);
#include <cstdarg>
#include <cstdio>
inline int ei_printf(const char *format, ...) {
    va_list args;
    va_start(args, format);
    const int n = vfprintf(stderr, format, args);
    va_end(args);
    return n;
}
#endif
