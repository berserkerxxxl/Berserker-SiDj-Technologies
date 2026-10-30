package main

import (
	"errors"
	"syscall"
)

func systemErrorKind(err error) string {
	// WinError.h codes; do not depend on the OS display language.
	// https://learn.microsoft.com/windows/win32/debug/system-error-codes--0-499-
	for _, item := range []struct {
		Code syscall.Errno
		Kind string
	}{
		{112, "disk_full"}, {39, "disk_full"}, {32, "busy"}, {33, "busy"},
		{19, "readonly"}, {21, "not_ready"}, {123, "invalid_path"},
		{206, "long_path"}, {23, "io"}, {29, "io"}, {30, "io"},
	} {
		if errors.Is(err, item.Code) {
			return item.Kind
		}
	}
	return ""
}
