package main

import (
	"bytes"
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

func TestDataLockExclusiveAndReleased(t *testing.T) {
	root := t.TempDir()
	unlock, err := lockData(root)
	if err != nil {
		t.Fatal(err)
	}
	second, err := lockData(root)
	if err == nil {
		second()
		unlock()
		t.Fatal("two processes could open the same archive for writing")
	}
	unlock()
	unlock, err = lockData(root)
	if err != nil {
		t.Fatal("archive could not be reopened after unlock:", err)
	}
	unlock()
}

func TestDefaultDataDirectory(t *testing.T) {
	exe := filepath.Join(t.TempDir(), "Read Only App", "B_S_Reserve")
	if runtime.GOOS == "windows" {
		root, err := defaultDataDir(exe)
		if err != nil || root != filepath.Join(filepath.Dir(exe), "Data") {
			t.Fatalf("Windows portable data path changed: %q %v", root, err)
		}
		return
	}
	home := t.TempDir()
	t.Setenv("HOME", home)
	xdg := t.TempDir()
	t.Setenv("XDG_DATA_HOME", xdg)
	root, err := defaultDataDir(exe)
	if err != nil || !filepath.IsAbs(root) || overlap(root, filepath.Dir(exe)) {
		t.Fatalf("user data must be independent of application directory: %q %v", root, err)
	}
	if runtime.GOOS == "linux" {
		if !overlap(root, xdg) {
			t.Fatal("XDG_DATA_HOME was ignored")
		}
		t.Setenv("XDG_DATA_HOME", "relative-path-must-be-ignored")
		root, err = defaultDataDir(exe)
		if err != nil || !overlap(root, home) {
			t.Fatalf("invalid XDG path was not replaced with user data directory: %q %v", root, err)
		}
	}
	if runtime.GOOS == "darwin" && !overlap(root, filepath.Join(home, "Library", "Application Support")) {
		t.Fatal("macOS data should be outside the app bundle in Application Support")
	}
}

func TestPlatformSecretProtection(t *testing.T) {
	secret := []byte("Synthetic test password; never a real credential")
	cipher, err := protectSecret(secret)
	if runtime.GOOS != "windows" {
		if err == nil || len(cipher) != 0 {
			t.Fatal("unsupported key storage silently accepted a plaintext password")
		}
		return
	}
	if err != nil || bytes.Contains(cipher, secret) {
		t.Fatalf("DPAPI protection failed: %v", err)
	}
	plain, err := unprotectSecret(cipher)
	if err != nil || !bytes.Equal(plain, secret) {
		t.Fatalf("DPAPI did not round-trip: %v", err)
	}
	cipher[len(cipher)/2] ^= 0xff
	if _, err = unprotectSecret(cipher); err == nil {
		t.Fatal("DPAPI accepted a modified blob")
	}
}

func TestUserDataDirectoryWritable(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("Windows keeps the existing portable directory beside the EXE")
	}
	t.Setenv("HOME", t.TempDir())
	t.Setenv("XDG_DATA_HOME", t.TempDir())
	root, err := defaultDataDir("/read-only/application/B_S_Reserve")
	if err != nil {
		t.Fatal(err)
	}
	if err = os.MkdirAll(root, 0700); err != nil {
		t.Fatal(err)
	}
	store, err := openStore(root)
	if err != nil {
		t.Fatal(err)
	}
	if err = store.AddNote("memory", "Synthetic platform test"); err != nil {
		t.Fatal(err)
	}
	if result := store.Verify(); len(result.Errors) != 0 {
		t.Fatal(result.Errors)
	}
}
