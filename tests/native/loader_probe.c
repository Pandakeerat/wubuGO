#include <windows.h>
#include <stdio.h>
typedef int (*fixture_fn)(void);
int main(void) {
    HMODULE module;
    fixture_fn value;
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
    module = LoadLibraryW(L"external_fixture.dll");
    if (!module) return 3;
    value = (fixture_fn)GetProcAddress(module, "fixture_value");
    if (!value) return 4;
    printf("%d\n", value());
    FreeLibrary(module);
    return 0;
}
