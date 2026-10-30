//go:build darwin || linux

package main

import (
	"fmt"
	"os"
	"strings"
	"syscall"
	"testing"
)

func TestRussianNativeUnixErrors(t *testing.T) {
	for code, word := range map[syscall.Errno]string{syscall.ENOSPC: "Недостаточно свободного места", syscall.EDQUOT: "объём хранения", syscall.EROFS: "защищён", syscall.EBUSY: "занят", syscall.EIO: "состояние носителя"} {
		err := fmt.Errorf("context: %w", &os.PathError{Op: "write", Path: "/synthetic/Vault/file", Err: code})
		if got := userError(err); !strings.Contains(got, word) {
			t.Fatal(code, got)
		}
	}
}
