package main

import (
	"errors"
	"time"
)

func validateScheduleTime(value string) error {
	if len(value) != 5 {
		return errors.New("укажите время в формате ЧЧ:ММ, от 00:00 до 23:59")
	}
	if _, err := time.Parse("15:04", value); err != nil {
		return errors.New("укажите время в формате ЧЧ:ММ, от 00:00 до 23:59")
	}
	return nil
}
