from django.db import models


class UserProfile(models.Model):
    cognito_id = models.CharField(max_length=255, unique=True)
    username = models.CharField(max_length=50, unique=True)
    email = models.EmailField(unique=True)
    interest_tags = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.username

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"
