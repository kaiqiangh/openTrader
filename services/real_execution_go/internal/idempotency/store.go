package idempotency

import (
	"sync"
	"time"
)

type Status string

const (
	StatusStarted   Status = "STARTED"
	StatusCompleted Status = "COMPLETED"
	StatusFailed    Status = "FAILED"
)

type Record struct {
	DispatchKey string
	Status      Status
	OrderID     string
	UpdatedAt   time.Time
	LastError   string
}

type Store interface {
	TryStart(dispatchKey string) bool
	MarkCompleted(dispatchKey string, orderID string)
	MarkFailed(dispatchKey string, lastError string)
	Get(dispatchKey string) (Record, bool)
}

type InMemoryStore struct {
	mu      sync.RWMutex
	records map[string]Record
	now     func() time.Time
}

func NewInMemoryStore() *InMemoryStore {
	return &InMemoryStore{
		records: make(map[string]Record),
		now:     time.Now,
	}
}

func (s *InMemoryStore) TryStart(dispatchKey string) bool {
	s.mu.Lock()
	defer s.mu.Unlock()

	if _, exists := s.records[dispatchKey]; exists {
		return false
	}
	s.records[dispatchKey] = Record{
		DispatchKey: dispatchKey,
		Status:      StatusStarted,
		UpdatedAt:   s.now().UTC(),
	}
	return true
}

func (s *InMemoryStore) MarkCompleted(dispatchKey string, orderID string) {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.records[dispatchKey] = Record{
		DispatchKey: dispatchKey,
		Status:      StatusCompleted,
		OrderID:     orderID,
		UpdatedAt:   s.now().UTC(),
	}
}

func (s *InMemoryStore) MarkFailed(dispatchKey string, lastError string) {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.records[dispatchKey] = Record{
		DispatchKey: dispatchKey,
		Status:      StatusFailed,
		UpdatedAt:   s.now().UTC(),
		LastError:   lastError,
	}
}

func (s *InMemoryStore) Get(dispatchKey string) (Record, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	record, exists := s.records[dispatchKey]
	return record, exists
}
