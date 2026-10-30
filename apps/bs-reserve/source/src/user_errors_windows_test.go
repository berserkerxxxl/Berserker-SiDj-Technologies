package main

import (
	"fmt"
	"os"
	"strings"
	"syscall"
	"testing"
)

func TestRussianNativeWindowsErrors(t *testing.T) {
	for _, code := range []syscall.Errno{112, 39} {
		for _, path := range []string{`C:\Synthetic Data\Vault\objects\.incoming-test`, `\\?\C:\Synthetic Data\Vault\objects\.incoming-test`} {
			err := fmt.Errorf("context: %w", &os.PathError{Op: "write", Path: path, Err: code})
			got := userError(err)
			if !strings.Contains(got, "на диске C:") || strings.Contains(got, "There is not") {
				t.Fatal("native disk code not localized", code, got)
			}
		}
	}
	for code, word := range map[syscall.Errno]string{32: "занят", 33: "занят", 19: "защищён", 21: "недоступен", 123: "Неверное имя"} {
		if got := userError(&os.PathError{Op: "write", Path: `E:\Synthetic`, Err: code}); !strings.Contains(got, word) {
			t.Fatal(code, got)
		}
	}
}
