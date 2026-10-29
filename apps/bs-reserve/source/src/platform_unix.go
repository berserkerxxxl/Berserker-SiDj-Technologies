//go:build darwin || linux

package main

import (
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
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
func installSchedule(exe, root, at string, atLogon bool) error {
	return errors.New("в этой альфе встроенное расписание доступно только в Windows")
}

func folderPickerAvailable() bool {
	if runtime.GOOS == "darwin" {
		return true
	}
	if os.Getenv("DISPLAY") == "" && os.Getenv("WAYLAND_DISPLAY") == "" {
		return false
	}
	for _, name := range []string{"zenity", "kdialog"} {
		if _, err := exec.LookPath(name); err == nil {
			return true
		}
	}
	return false
}
func pickFolder(ctx context.Context, initial string) (string, error) {
	var cmd *exec.Cmd
	if runtime.GOOS == "darwin" {
		if info, err := os.Stat(initial); err != nil || !info.IsDir() {
			initial = ""
		}
		script := "on run argv\nif (item 1 of argv) is \"\" then\nset selected to choose folder with prompt \"B/S Reserve: выберите папку\"\nelse\nset selected to choose folder with prompt \"B/S Reserve: выберите папку\" default location (POSIX file (item 1 of argv))\nend if\nreturn POSIX path of selected\nend run"
		cmd = exec.CommandContext(ctx, "/usr/bin/osascript", "-e", script, initial)
	} else {
		if !folderPickerAvailable() {
			return "", errors.New("для выбора папки нужен графический сеанс и zenity или kdialog; путь можно ввести вручную")
		}
		if p, err := exec.LookPath("zenity"); err == nil {
			args := []string{"--file-selection", "--directory", "--title=B/S Reserve: выберите папку"}
			if initial != "" {
				args = append(args, "--filename="+initial+string(filepath.Separator))
			}
			cmd = exec.CommandContext(ctx, p, args...)
		} else {
			cmd = exec.CommandContext(ctx, "kdialog", "--getexistingdirectory", initial, "--title", "B/S Reserve: выберите папку")
		}
	}
	out, err := cmd.Output()
	if err != nil {
		if exit, ok := err.(*exec.ExitError); ok && (exit.ExitCode() == 1 || strings.Contains(string(exit.Stderr), "(-128)")) {
			return "", nil
		}
		return "", errors.New("не удалось открыть выбор папки; укажите путь вручную")
	}
	return strings.TrimSpace(string(out)), nil
}
