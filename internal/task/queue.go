package task

import "container/heap"

type queueItem struct {
	task     ScraperTask
	sequence uint64
	index    int
}

type priorityQueue []*queueItem

func (q priorityQueue) Len() int { return len(q) }

func (q priorityQueue) Less(i, j int) bool {
	if q[i].task.Priority != q[j].task.Priority {
		return q[i].task.Priority > q[j].task.Priority
	}
	return q[i].sequence < q[j].sequence
}

func (q priorityQueue) Swap(i, j int) {
	q[i], q[j] = q[j], q[i]
	q[i].index = i
	q[j].index = j
}

func (q *priorityQueue) Push(value any) {
	item := value.(*queueItem)
	item.index = len(*q)
	*q = append(*q, item)
}

func (q *priorityQueue) Pop() any {
	old := *q
	item := old[len(old)-1]
	old[len(old)-1] = nil
	item.index = -1
	*q = old[:len(old)-1]
	return item
}

func (q *priorityQueue) pushTask(task ScraperTask, sequence uint64) {
	heap.Push(q, &queueItem{task: task, sequence: sequence})
}

func (q *priorityQueue) popTask() ScraperTask {
	return heap.Pop(q).(*queueItem).task
}

func (q *priorityQueue) removeTask(taskID string) bool {
	for _, item := range *q {
		if item.task.ID == taskID {
			heap.Remove(q, item.index)
			return true
		}
	}
	return false
}
