from django import forms
from django.conf import settings

from .models import Photo


class PhotoForm(forms.ModelForm):
    class Meta:
        model = Photo
        fields = ["image", "caption"]

    def clean_image(self):
        image = self.cleaned_data["image"]
        if image.size > settings.MAX_PHOTO_UPLOAD_BYTES:
            limit_mb = settings.MAX_PHOTO_UPLOAD_BYTES // (1024 * 1024)
            raise forms.ValidationError(f"That photo is larger than {limit_mb} MB.")
        return image
