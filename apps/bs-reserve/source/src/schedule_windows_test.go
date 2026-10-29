package main

import (
	"bytes"
	"encoding/xml"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestWindowsScheduleRegistration(t *testing.T) {
	if os.Getenv("BS_TEST_SCHEDULER") != "1" {
		t.Skip("set BS_TEST_SCHEDULER=1 to test an isolated temporary Windows task")
	}
	root := filepath.Join(t.TempDir(), "Проверка расписания")
	exe, _ := os.Executable()
	name := scheduleTaskName(root)
	t.Cleanup(func() {
		cleanup := "Unregister-ScheduledTask -TaskName " + psQuote(name) + " -Confirm:$false -ErrorAction SilentlyContinue"
		_ = exec.Command("powershell.exe", powerShellArgs(cleanup)...).Run()
	})
	for _, hours := range []int{12, 13} {
		at := time.Now().Add(time.Duration(hours) * time.Hour).Format("15:04")
		if err := installSchedule(exe, root, at, false); err != nil {
			t.Fatal(err)
		}
		query := "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); [Console]::Write((Export-ScheduledTask -TaskName " + psQuote(name) + "))"
		output, err := exec.Command("powershell.exe", powerShellArgs(query)...).Output()
		if err != nil {
			t.Fatal(err)
		}
		// Export-ScheduledTask declares UTF-16, while Console writes UTF-8.
		if end := bytes.Index(output, []byte("?>")); bytes.HasPrefix(output, []byte("<?xml")) && end >= 0 {
			output = output[end+2:]
		}
		var task struct {
			Triggers struct {
				CalendarTrigger []struct{ StartBoundary string }
				LogonTrigger    []struct{}
			}
			Actions struct {
				Exec struct{ Command, Arguments string }
			}
		}
		if err = xml.Unmarshal(output, &task); err != nil {
			t.Fatal(err)
		}
		if len(task.Triggers.CalendarTrigger) != 1 || !strings.Contains(task.Triggers.CalendarTrigger[0].StartBoundary, "T"+at+":") || len(task.Triggers.LogonTrigger) != 0 {
			t.Fatal("time or at-logon selection was not applied")
		}
		if task.Actions.Exec.Command != exe || !strings.Contains(task.Actions.Exec.Arguments, root) {
			t.Fatal("task action does not point to selected executable and data")
		}
	}
	script, err := scheduleScript(exe, root, "07:15", true)
	if err != nil || !strings.Contains(script, "-At '07:15'") || !strings.Contains(script, "-AtLogOn") {
		t.Fatal("startup trigger was omitted", err)
	}
	quoted := `C:\Test O'Brien\Data`
	if !strings.Contains(folderPickerScript(quoted), psQuote(quoted)) {
		t.Fatal("folder picker path was not quoted")
	}
}
