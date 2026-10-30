package main

import (
	"context"
	"encoding/base64"
	"encoding/binary"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"unicode/utf16"
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
		return nil, errors.New("Программа B/S Reserve уже запущена или данные заняты")
	}
	return func() { syscall.CloseHandle(h) }, nil
}
func psQuote(s string) string { return "'" + strings.ReplaceAll(s, "'", "''") + "'" }
func scheduleTaskName(root string) string {
	return "BS_Reserve_" + sum([]byte(strings.ToLower(root)))[:10]
}
func powerShellArgs(script string) []string {
	units := utf16.Encode([]rune(script))
	bytes := make([]byte, len(units)*2)
	for i, unit := range units {
		binary.LittleEndian.PutUint16(bytes[i*2:], unit)
	}
	return []string{"-NoProfile", "-STA", "-EncodedCommand", base64.StdEncoding.EncodeToString(bytes)}
}
func scheduleScript(exe, root, at string, atLogon bool) (string, error) {
	if err := validateScheduleTime(at); err != nil {
		return "", err
	}
	name := scheduleTaskName(root)
	arguments := "--run-once --data \"" + root + "\""
	triggers := "$t=@((New-ScheduledTaskTrigger -Daily -At " + psQuote(at) + ")"
	if atLogon {
		triggers += ",(New-ScheduledTaskTrigger -AtLogOn -User $u)"
	}
	triggers += "); "
	script := "$ErrorActionPreference='Stop'; " +
		"$u=[System.Security.Principal.WindowsIdentity]::GetCurrent().Name; " +
		"$a=New-ScheduledTaskAction -Execute " + psQuote(exe) + " -Argument " + psQuote(arguments) + "; " +
		triggers +
		"$p=New-ScheduledTaskPrincipal -UserId $u -LogonType Interactive -RunLevel Limited; " +
		"$s=New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew; " +
		"Register-ScheduledTask -TaskName " + psQuote(name) + " -Action $a -Trigger $t -Principal $p -Settings $s -Description 'B/S Reserve: local import and encrypted backup' -Force | Out-Null"
	return script, nil
}
func installSchedule(exe, root, at string, atLogon bool) error {
	script, err := scheduleScript(exe, root, at, atLogon)
	if err != nil {
		return err
	}
	cmd := exec.Command("powershell.exe", powerShellArgs(script)...)
	hideCommand(cmd)
	if _, err := cmd.CombinedOutput(); err != nil {
		return errors.New("Windows не разрешила создать задачу; запустите импорт вручную или настройте Планировщик")
	}
	return nil
}

func folderPickerAvailable() bool { return true }
func folderPickerScript(initial string) string {
	return "$ErrorActionPreference='Stop'; Add-Type -AssemblyName System.Windows.Forms; " +
		"[System.Windows.Forms.Application]::EnableVisualStyles(); " +
		"$d=New-Object System.Windows.Forms.FolderBrowserDialog; " +
		"$o=New-Object System.Windows.Forms.Form; $o.ShowInTaskbar=$false; " +
		"$o.FormBorderStyle=[System.Windows.Forms.FormBorderStyle]::None; " +
		"$o.StartPosition=[System.Windows.Forms.FormStartPosition]::CenterScreen; " +
		"$o.Size=[System.Drawing.Size]::new(1,1); $o.Opacity=0; " +
		"try { $d.Description='B/S Reserve: выберите папку'; $d.ShowNewFolderButton=$true; " +
		"$p=" + psQuote(initial) + "; if([System.IO.Directory]::Exists($p)){$d.SelectedPath=$p}; " +
		// A TopMost property on an owner that was never shown does not reliably
		// give SHBrowseForFolder a topmost owner. Create/show its actual HWND
		// before setting TopMost; the owned native dialog inherits that z-order.
		"$o.Show(); $o.TopMost=$true; $o.Activate(); $o.BringToFront(); " +
		"[System.Windows.Forms.Application]::DoEvents(); " +
		"if($d.ShowDialog($o) -eq [System.Windows.Forms.DialogResult]::OK){" +
		"[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); [Console]::Write($d.SelectedPath)" +
		"} } finally { $d.Dispose(); $o.Close(); $o.Dispose() }"
}
func pickFolder(ctx context.Context, initial string) (string, error) {
	if initial == "" {
		initial, _ = os.UserHomeDir()
	}
	cmd := exec.CommandContext(ctx, "powershell.exe", powerShellArgs(folderPickerScript(initial))...)
	hideCommand(cmd)
	out, err := cmd.Output()
	if err != nil {
		return "", errors.New("не удалось открыть выбор папки; укажите путь вручную")
	}
	return strings.TrimSpace(strings.TrimPrefix(string(out), "\ufeff")), nil
}
