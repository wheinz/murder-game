from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Photo


@receiver(post_delete, sender=Photo)
def delete_photo_file(sender, instance, **kwargs):
    """Remove the image file from disk when a Photo row is deleted (incl. bulk deletes)."""
    if instance.image:
        instance.image.delete(save=False)
