from trips.models import Task, TaskTemplate, TaskTemplatePack


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


class WorkTaskTemplatePack(TaskTemplatePack):
    class Meta:
        proxy = True
        verbose_name = "Task Template Pack"
        verbose_name_plural = "Task Template Packs"
