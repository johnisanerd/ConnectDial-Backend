import io
import os
import tempfile
from django.contrib import admin
from django.core.files.base import ContentFile, File
from django.core.files.uploadedfile import InMemoryUploadedFile

from .models import ShortVideo, VideoLike, VideoComment, CommentMention, VideoShare, VideoView
from .video_processing import compress_video, extract_duration, generate_thumbnail


class ShortVideoAdmin(admin.ModelAdmin):
    list_display = ('id', 'author', 'caption', 'duration', 'created_at', 'status')
    ordering = ['-created_at']
    readonly_fields = ('duration', 'cached_likes', 'cached_comments', 
                      'cached_shares', 'cached_views')

    def save_model(self, request, obj, form, change):
        """
        Handle video compression + metadata extraction when uploading 
        or replacing video via Django Admin.
        """
        video_file = form.cleaned_data.get('video')

        if video_file and 'video' in form.changed_data:
            tmp_path = None
            compressed_path = None

            try:
                # 1. Save uploaded file to temp disk
                with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp:
                    for chunk in video_file.chunks():
                        tmp.write(chunk)
                    tmp_path = tmp.name

                # 2. Compress video
                compressed_path = tmp_path + '_compressed.mp4'
                compress_video(tmp_path, compressed_path)

                # 3. Extract duration
                obj.duration = extract_duration(compressed_path)

                # 4. IMPORTANT: Use Django's File() instead of InMemoryUploadedFile for GCS
                with open(compressed_path, 'rb') as f:
                    django_file = File(f, name=video_file.name or 'video.mp4')
                    obj.video = django_file   # ← Better for GoogleCloudStorage

                # 5. Generate thumbnail if missing
                if not obj.thumbnail:
                    try:
                        thumb_bytes = generate_thumbnail(compressed_path)
                        obj.thumbnail.save(
                            f'thumb_{obj.pk or "new"}.jpg',
                            ContentFile(thumb_bytes),
                            save=False
                        )
                    except Exception as e:
                        print(f"Thumbnail generation failed: {e}")

            except Exception as e:
                print(f"Video processing failed in admin: {e}")
                # Optionally re-raise or show message to admin user
            finally:
                # Cleanup temp files
                for path in (tmp_path, compressed_path):
                    if path and os.path.exists(path):
                        try:
                            os.unlink(path)
                        except OSError:
                            pass

        # Final save
        super().save_model(request, obj, form, change)


# Register models
admin.site.register(ShortVideo, ShortVideoAdmin)
admin.site.register(VideoLike)
admin.site.register(VideoComment)
admin.site.register(CommentMention)
admin.site.register(VideoShare)
admin.site.register(VideoView)