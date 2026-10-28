//go:build darwin || linux

package main

import (
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"syscall"
)

func protectSecret(b []byte) ([]byte, error) {
	return nil, errors.New("сохранение ключа доступно только в Windows; введите пароль для операции")
}
func unprotectSecret(b []byte) ([]byte, error) {
	return nil, errors.New("ключ Windows DPAPI нельзя открыть на macOS или Linux; введите аварийный пароль")
}
func hideCommand(c *exec.Cmd) {}
func openBrowser(url string) {
	name := "xdg-open"
	if runtime.GOOS == "darwin" {
		name = "/usr/bin/open"
	} else if os.Getenv("DISPLAY") == "" && os.Getenv("WAYLAND_DISPLAY") == "" {
		return // The URL is already printed by main for a terminal or headless host.
	}
	cmd := exec.Command(name, url)
	if err := cmd.Start(); err == nil {
		go cmd.Wait()
	}
}
func showError(text string) {
	fmt.Fprintln(os.Stderr, text)
	if runtime.GOOS == "darwin" {
		// Arguments are passed separately; no shell or AppleScript interpolation.
		script := "on run argv\ndisplay alert \"B/S Reserve\" message (item 1 of argv) as critical\nend run"
		_ = exec.Command("/usr/bin/osascript", "-e", script, text).Run()
	}
}
func lockData(root string) (func(), error) {
	f, err := os.OpenFile(filepath.Join(root, "reserve.lock"), os.O_CREATE|os.O_RDWR, 0600)
	if err != nil {
		return nil, err
	}
	if err = syscall.Flock(int(f.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
		f.Close()
		return nil, errors.New("данные заняты другим процессом")
	}
	return func() { syscall.Flock(int(f.Fd()), syscall.LOCK_UN); f.Close() }, nil
}
func installSchedule(exe, root string) error {
	return errors.New("в этой альфе встроенное расписание доступно только в Windows")
}
