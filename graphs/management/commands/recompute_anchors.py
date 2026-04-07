from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from graphs.models import UserGraph
from graphs.services.graph import _full_anchor_recompute


class Command(BaseCommand):
    help = "Recompute anchor embeddings for recently active users to correct incremental drift."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=7,
            help="Only recompute users active within this many days (default: 7).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print which users would be updated without making any changes.",
        )

    def handle(self, *args, **options):
        days = options["days"]
        dry_run = options["dry_run"]
        cutoff = timezone.now() - timedelta(days=days)

        # Only recompute users who have a cached anchor and were active recently
        graphs = UserGraph.objects.filter(
            cached_anchor__isnull=False,
            anchor_updated_at__gte=cutoff,
        ).select_related("user")

        total = graphs.count()
        self.stdout.write(f"Found {total} user(s) active in the last {days} days.")

        if dry_run:
            for graph in graphs:
                self.stdout.write(f"  [dry-run] Would recompute: {graph.user.username}")
            return

        updated = 0
        failed = 0
        for graph in graphs:
            try:
                anchor, total_weight = _full_anchor_recompute(graph.user)
                graph.cached_anchor = anchor
                graph.cached_total_weight = total_weight
                graph.anchor_updated_at = timezone.now()
                graph.save(update_fields=["cached_anchor", "cached_total_weight", "anchor_updated_at"])
                updated += 1
                self.stdout.write(f"  Recomputed: {graph.user.username}")
            except Exception as e:
                failed += 1
                self.stderr.write(f"  Failed for {graph.user.username}: {e}")

        self.stdout.write(self.style.SUCCESS(f"Done. {updated} updated, {failed} failed."))
