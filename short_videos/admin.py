import io
import os
import tempfile
from django.contrib import admin
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import InMemoryUploadedFile

from .models import ShortVideo, VideoLike, VideoComment, CommentMention, VideoShare, VideoView
# Importing from our newly isolated processing module to protect utils.py
from .video_processing import compress_video, extract_duration, generate_thumbnail

class ShortVideoAdmin(admin.ModelAdmin):
    list_display = ('id', 'author', 'caption', 'duration', 'created_at')
    ordering = ['-created_at']

    def save_model(self, request, obj, form, change):
        """
        Intercept admin form saves to fully compress, process, and extract metadata
        for files manually uploaded inside the ConnectDial Admin Portal.
        """
        video_file = form.cleaned_data.get('video')

        # Run optimization only if a brand new file has been submitted or replaced
        if video_file and 'video' in form.changed_data:
            tmp_path = None
            compressed_path = None

            try:
                # 1. Stream file chunks into system temporary files
                with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp:
                    for chunk in video_file.chunks():
                        tmp.write(chunk)
                    tmp_path = tmp.name

                # 2. Run your compression and +faststart optimization
                compressed_path = tmp_path + '_compressed.mp4'
                compress_video(tmp_path, compressed_path)

                # 3. Read video file length natively via ffprobe
                obj.duration = extract_duration(compressed_path)

                # 4. Read the optimized compressed bytes back into an active buffer
                with open(compressed_path, 'rb') as cf:
                    compressed_content = cf.read()

                # 5. Package bytes back into standard Django files and overwrite original field
                obj.video = InMemoryUploadedFile(
                    file=io.BytesIO(compressed_content),
                    field_name='video',
                    name=video_file.name,
                    content_type='video/mp4',
                    size=len(compressed_content),
                    charset=None
                )

                # 6. Fallback automatic thumbnail generator routine if none provided
                if not obj.thumbnail:
                    try:
                        thumb_bytes = generate_thumbnail(compressed_path)
                        obj.thumbnail.save(
                            f'thumb_{obj.pk}.jpg',
                            ContentFile(thumb_bytes),
                            save=False  # Keep it False; let admin pipeline commit it natively
                        )
                    except Exception:
                        pass

            finally:
                # Clean up system files off the server disk
                for path in (tmp_path, compressed_path):
                    if path and os.path.exists(path):
                        try:
                            os.unlink(path)
                        except OSError:
                            pass

        # Execute built-in Django database commit routines
        super().save_model(request, obj, form, change)


admin.site.register(ShortVideo, ShortVideoAdmin)
admin.site.register(VideoLike)
admin.site.register(VideoComment)
admin.site.register(CommentMention)
admin.site.register(VideoShare)
admin.site.register(VideoView)