"""
delete_bot_posts.py
Place at: <app>/management/commands/delete_bot_posts.py

Usage:
  python manage.py delete_bot_posts --dry-run
  python manage.py delete_bot_posts --yes
  python manage.py delete_bot_posts --yes --league "Premier League"
  python manage.py delete_bot_posts --yes --with-media
"""

from django.core.management.base import BaseCommand
from posts.models import Post


class Command(BaseCommand):
    help = "Deletes all posts authored by bots"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Show count only, delete nothing")
        parser.add_argument("--yes", action="store_true",
                            help="Skip confirmation prompt")
        parser.add_argument("--with-media", action="store_true",
                            help="Also delete media files from Firebase storage")
        parser.add_argument("--league", type=str, default=None,
                            help="Only delete posts from this league")

    def handle(self, *args, **options):
        qs = Post.objects.filter(author__profile__is_bot=True)

        if options["league"]:
            qs = qs.filter(league__name__icontains=options["league"])

        count = qs.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS("✅ No bot posts found."))
            return

        if options["dry_run"]:
            self.stdout.write(f"[DRY RUN] Would delete {count} bot post(s). Nothing changed.")
            return

        if not options["yes"]:
            confirm = input(f"⚠️  Delete {count} bot post(s)? Type 'yes' to confirm: ")
            if confirm.strip().lower() != "yes":
                self.stdout.write("Aborted.")
                return

        if options["with_media"]:
            self.stdout.write("🗑️  Removing media files...")
            cleared = 0
            for post in qs.exclude(media_file="").exclude(media_file__isnull=True).iterator():
                try:
                    post.media_file.delete(save=False)
                    cleared += 1
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"  ⚠️  {post.id}: {e}"))
            self.stdout.write(f"   {cleared} media file(s) removed from storage.")

        deleted, _ = qs.delete()
        self.stdout.write(self.style.SUCCESS(f"✅ Deleted {count} bot post(s)."))