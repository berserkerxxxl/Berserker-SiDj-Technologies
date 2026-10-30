//go:build darwin || linux

package main

import (
	"errors"
	"syscall"
)

func systemErrorKind(err error) string {
	for _, item := range []struct {
		Code syscall.Errno
		Kind string
	}{
		{syscall.ENOSPC, "disk_full"}, {syscall.EDQUOT, "quota"},
		{syscall.EBUSY, "busy"}, {syscall.ETXTBSY, "busy"}, {syscall.EROFS, "readonly"},
		{syscall.ENAMETOOLONG, "long_path"}, {syscall.EIO, "io"},
	} {
		if errors.Is(err, item.Code) {
			return item.Kind
		}
	}
	return ""
}
