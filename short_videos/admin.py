import io
import os
import tempfile
from django.contrib import admin
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import InMemoryUploadedFile
from .models import ShortVideo, VideoLike, VideoComment, CommentMention, VideoShare, VideoView
# Import your utility functions here
from .views import compress_video, extract_duration, generate_thumbnail 

class ShortVideoAdmin(admin.ModelAdmin):
    # Display important data columns in the admin list view
    list_display = ('id', 'author', 'duration', 'created_at')

    def save_model(self, request, obj, form, change):
        """
        Intercept the admin save pipeline to compress video and extract duration 
        mirroring the DRF API upload view behavior.
        """
        video_file = form.cleaned_data.get('video')
        
        # Check if a new video file was uploaded via the admin interface
        if video_file and 'video' in form.changed_data:
            tmp_path = None
            compressed_path = None
            
            try:
                # 1. Write the uploaded chunks to a temporary system file
                with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp:
                    for chunk in video_file.chunks():
                        tmp.write(chunk)
                    tmp_path = tmp.name

                # 2. Run your compression and +faststart flag toolchain
                compressed_path = tmp_path + '_compressed.mp4'
                compress_video(tmp_path, compressed_path)

                # 3. Read metadata variables using ffprobe
                obj.duration = extract_duration(compressed_path)

                # 4. Read compressed bytes back into memory
                with open(compressed_path, 'rb') as cf:
                    compressed_content = cf.read()

                # 5. Overwrite the raw field file with the processed version
                obj.video = InMemoryUploadedFile(
                    file=io.BytesIO(compressed_content),
                    field_name='video',
                    name=video_file.name,
                    content_type='video/mp4',
                    size=len(compressed_content),
                    charset=None
                )

                # 6. Auto-generate a video thumbnail if missing
                if not obj.thumbnail:
                    try:
                        thumb_bytes = generate_thumbnail(compressed_path)
                        obj.thumbnail.save(
                            f'thumb_{obj.pk}.jpg',
                            ContentFile(thumb_bytes),
                            save=False # Avoid committing early
                        )
                    except Exception:
                        pass

            finally:
                # Cleanup local temp files on disk
                for path in (tmp_path, compressed_path):
                    if path and os.path.exists(path):
                        try:
                            os.unlink(path)
                        except OSError:
                            pass

        # Complete standard Django saving procedures
        super().save_model(request, obj, form, change)

# Register with the custom administration controller
admin.site.register(ShortVideo, ShortVideoAdmin)

# Register the remaining items
admin.site.register(VideoLike)
admin.site.register(VideoComment)
admin.site.register(CommentMention)
admin.site.register(VideoShare)
admin.site.register(VideoView)