from trips.models import Task, TaskTemplate


class WorkTask(Task):
    class Meta:
        proxy = True
        verbose_name = "Task"
        verbose_name_plural = "Tasks"


class WorkTaskTemplate(TaskTemplate):
    class Meta:
        proxy = True
        verbose_name = "Task Template"
        verbose_name_plural = "Task Templates"

