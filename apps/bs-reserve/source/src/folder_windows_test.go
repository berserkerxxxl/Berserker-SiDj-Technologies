package main

import (
	"bytes"
	"context"
	"os"
	"os/exec"
	"strings"
	"syscall"
	"testing"
	"time"
	"unsafe"
)

func TestWindowsFolderDialogTopmostAndCancel(t *testing.T) {
	if os.Getenv("BS_TEST_FOLDER_DIALOG") != "1" {
		t.Skip("set BS_TEST_FOLDER_DIALOG=1 for the native Windows dialog check")
	}
	interactive, err := exec.Command("powershell.exe", powerShellArgs("[Console]::Write([Environment]::UserInteractive)")...).Output()
	if err != nil {
		t.Fatal(err)
	}
	if !strings.EqualFold(strings.TrimSpace(string(interactive)), "true") {
		t.Skip("runner has no interactive Windows desktop")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, "powershell.exe", powerShellArgs(folderPickerScript(t.TempDir()))...)
	hideCommand(cmd)
	var stdout, stderr bytes.Buffer
	cmd.Stdout, cmd.Stderr = &stdout, &stderr
	if err = cmd.Start(); err != nil {
		t.Fatal(err)
	}
	done := make(chan error, 1)
	go func() { done <- cmd.Wait() }()
	exited := false
	defer func() {
		cancel()
		if exited {
			return
		}
		select {
		case <-done:
		case <-time.After(5 * time.Second):
		}
	}()
	user32 := syscall.NewLazyDLL("user32.dll")
	enumerate := user32.NewProc("EnumWindows")
	getPID := user32.NewProc("GetWindowThreadProcessId")
	getClass := user32.NewProc("GetClassNameW")
	visible := user32.NewProc("IsWindowVisible")
	getStyle := user32.NewProc("GetWindowLongPtrW")
	getOwner := user32.NewProc("GetWindow")
	var dialog uintptr
	callback := syscall.NewCallback(func(hwnd, unused uintptr) uintptr {
		var pid uint32
		getPID.Call(hwnd, uintptr(unsafe.Pointer(&pid)))
		if pid != uint32(cmd.Process.Pid) {
			return 1
		}
		var class [256]uint16
		getClass.Call(hwnd, uintptr(unsafe.Pointer(&class[0])), uintptr(len(class)))
		shown, _, _ := visible.Call(hwnd)
		if shown != 0 && syscall.UTF16ToString(class[:]) == "#32770" {
			dialog = hwnd
			return 0
		}
		return 1
	})
	deadline := time.Now().Add(20 * time.Second)
	for dialog == 0 && time.Now().Before(deadline) {
		enumerate.Call(callback, 0)
		if dialog != 0 {
			break
		}
		select {
		case err = <-done:
			exited = true
			t.Fatalf("picker exited before showing its dialog: %v %s", err, stderr.String())
		default:
		}
		time.Sleep(100 * time.Millisecond)
	}
	if dialog == 0 {
		t.Fatal("native folder dialog was not shown")
	}
	style, _, _ := getStyle.Call(dialog, ^uintptr(19)) // GWL_EXSTYLE = -20.
	owner, _, _ := getOwner.Call(dialog, 4)            // GW_OWNER.
	ownerVisible, _, _ := visible.Call(owner)
	ownerStyle, _, _ := getStyle.Call(owner, ^uintptr(19))
	if owner == 0 || ownerVisible == 0 || style&8 == 0 || ownerStyle&8 == 0 {
		t.Fatal("folder dialog and its visible owner must both be topmost")
	}
	// A browser AbortController cancels the HTTP context and closes this process.
	cancel()
	select {
	case <-done:
		exited = true
	case <-time.After(5 * time.Second):
		t.Fatal("cancelled picker process did not exit")
	}
	shown, _, _ := visible.Call(dialog)
	if shown != 0 {
		t.Fatal("cancellation left an orphaned topmost dialog")
	}
}
