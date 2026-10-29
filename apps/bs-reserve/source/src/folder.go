package main

import (
	"encoding/json"
	"errors"
	"net/http"
	"strings"
)

func (a *App) chooseFolder(w http.ResponseWriter, r *http.Request) {
	if r.Method != "POST" {
		fail(w, 405, errors.New("нужен POST"))
		return
	}
	r.Body = http.MaxBytesReader(w, r.Body, 16<<10)
	var req struct{ Initial string }
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		fail(w, 400, err)
		return
	}
	if !a.pickerMu.TryLock() {
		fail(w, 409, errors.New("диалог выбора папки уже открыт"))
		return
	}
	defer a.pickerMu.Unlock()
	choose := a.picker
	if choose == nil {
		choose = pickFolder
	}
	selected, err := choose(r.Context(), strings.TrimSpace(req.Initial))
	if err != nil {
		fail(w, 400, err)
		return
	}
	respond(w, map[string]any{"Path": selected, "Cancelled": selected == ""})
}
