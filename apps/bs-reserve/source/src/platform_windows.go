package main

import (
	"errors"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"unsafe"
)

type dataBlob struct {
	Size uint32
	Data *byte
}

var crypt32 = syscall.NewLazyDLL("crypt32.dll")
var kernel32 = syscall.NewLazyDLL("kernel32.dll")

func cryptSecret(b []byte, decrypt bool) ([]byte, error) {
	if len(b) == 0 {
		return nil, errors.New("пустой секрет")
	}
	in := dataBlob{Size: uint32(len(b)), Data: &b[0]}
	var out dataBlob
	name := "CryptProtectData"
	if decrypt {
		name = "CryptUnprotectData"
	}
	ok, _, err := crypt32.NewProc(name).Call(uintptr(unsafe.Pointer(&in)), 0, 0, 0, 0, 1, uintptr(unsafe.Pointer(&out)))
	if ok == 0 {
		return nil, err
	}
	defer kernel32.NewProc("LocalFree").Call(uintptr(unsafe.Pointer(out.Data)))
	result := append([]byte(nil), unsafe.Slice(out.Data, int(out.Size))...)
	return result, nil
}
func protectSecret(b []byte) ([]byte, error)   { return cryptSecret(b, false) }
func unprotectSecret(b []byte) ([]byte, error) { return cryptSecret(b, true) }
func hideCommand(c *exec.Cmd)                  { c.SysProcAttr = &syscall.SysProcAttr{HideWindow: true} }
func openBrowser(url string) {
	_ = exec.Command("rundll32.exe", "url.dll,FileProtocolHandler", url).Start()
}
func showError(text string) {
	t, _ := syscall.UTF16PtrFromString(text)
	title, _ := syscall.UTF16PtrFromString("B/S Reserve")
	syscall.NewLazyDLL("user32.dll").NewProc("MessageBoxW").Call(0, uintptr(unsafe.Pointer(t)), uintptr(unsafe.Pointer(title)), 0x10)
}
func lockData(root string) (func(), error) {
	p, _ := syscall.UTF16PtrFromString(filepath.Join(root, "reserve.lock"))
	h, err := syscall.CreateFile(p, syscall.GENERIC_READ|syscall.GENERIC_WRITE, 0, nil, syscall.OPEN_ALWAYS, syscall.FILE_ATTRIBUTE_NORMAL, 0)
	if err != nil {
		return nil, errors.New("B/S Reserve уже запущен или данные заняты")
	}
	return func() { syscall.CloseHandle(h) }, nil
}
func psQuote(s string) string { return "'" + strings.ReplaceAll(s, "'", "''") + "'" }
func installSchedule(exe, root string) error {
	name := "BS_Reserve_" + sum([]byte(strings.ToLower(root)))[:10]
	arguments := "--run-once --data \"" + root + "\""
	script := "$ErrorActionPreference='Stop'; " +
		"$u=[System.Security.Principal.WindowsIdentity]::GetCurrent().Name; " +
		"$a=New-ScheduledTaskAction -Execute " + psQuote(exe) + " -Argument " + psQuote(arguments) + "; " +
		"$t=@((New-ScheduledTaskTrigger -Daily -At '19:00'),(New-ScheduledTaskTrigger -AtLogOn -User $u)); " +
		"$p=New-ScheduledTaskPrincipal -UserId $u -LogonType Interactive -RunLevel Limited; " +
		"$s=New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew; " +
		"Register-ScheduledTask -TaskName " + psQuote(name) + " -Action $a -Trigger $t -Principal $p -Settings $s -Description 'B/S Reserve: local import and encrypted backup' -Force | Out-Null"
	cmd := exec.Command("powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script)
	hideCommand(cmd)
	if _, err := cmd.CombinedOutput(); err != nil {
		return errors.New("Windows не разрешила создать задачу; запустите импорт вручную или настройте Планировщик")
	}
	return nil
}
