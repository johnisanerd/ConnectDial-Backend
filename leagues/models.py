from django.db import models
from django.core.exceptions import ValidationError


class League(models.Model):
    """
    Represents a sports league, e.g., NBA, EPL
    """
    id = models.IntegerField(primary_key=True)
    name = models.CharField(max_length=100, unique=True)
    abbreviation = models.CharField(max_length=10, blank=True)
    logo = models.ImageField(upload_to='league_logos/', blank=True, null=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.id:
            raise ValidationError("You must provide a manual ID for this League.")
        super().save(*args, **kwargs)


class Team(models.Model):
    """
    Represents a sports team belonging to a league.
    Name is unique *within* a league, not globally — the same team name
    (e.g. "Real Madrid", "England") can legitimately exist across
    different leagues/competitions.
    """
    id = models.IntegerField(primary_key=True)

    name = models.CharField(max_length=100)
    league = models.ForeignKey(
        League,
        on_delete=models.CASCADE,
        related_name='teams'
    )
    logo = models.ImageField(upload_to='team_logos/', blank=True, null=True)

    class Meta:
        unique_together = ('league', 'name')

    def __str__(self):
        return f"{self.name} ({self.league.abbreviation})"

    def save(self, *args, **kwargs):
        if not self.id:
            raise ValidationError("You must provide a manual ID for this Team.")
        super().save(*args, **kwargs)