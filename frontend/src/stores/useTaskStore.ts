import { create } from 'zustand'
import type { Task, TaskStatus } from '@/types/task'

interface TaskState {
  /** 任务列表 */
  tasks: Task[]
  /** 当前选中的任务 */
  selectedTask: Task | null
  /** 正在执行中的任务 ID 集合 */
  runningTaskIds: Set<number>
  /** 任务总数 */
  total: number

  setTasks: (tasks: Task[], total: number) => void
  selectTask: (task: Task | null) => void
  addTask: (task: Task) => void
  updateTaskStatus: (taskId: number, status: TaskStatus) => void
  setRunning: (taskId: number, running: boolean) => void
}

export const useTaskStore = create<TaskState>((set) => ({
  tasks: [],
  selectedTask: null,
  runningTaskIds: new Set(),
  total: 0,

  setTasks: (tasks, total) => set({ tasks, total }),
  selectTask: (selectedTask) => set({ selectedTask }),

  addTask: (task) =>
    set((state) => ({
      tasks: [task, ...state.tasks],
      total: state.total + 1,
    })),

  updateTaskStatus: (taskId, status) =>
    set((state) => ({
      tasks: state.tasks.map((t) =>
        t.id === taskId ? { ...t, status, updatedAt: Date.now() / 1000 } : t,
      ),
    })),

  setRunning: (taskId, running) =>
    set((state) => {
      const next = new Set(state.runningTaskIds)
      if (running) {
        next.add(taskId)
      } else {
        next.delete(taskId)
      }
      return { runningTaskIds: next }
    }),
}))
