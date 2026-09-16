from rest_framework import serializers

from connectdial.media import build_media_url
from .models import League, Team


class TeamSerializer(serializers.ModelSerializer):
    logo = serializers.SerializerMethodField()

    class Meta:
        model = Team
        fields = ['id', 'name', 'logo', 'league']

    def get_logo(self, obj):
        return build_media_url(obj.logo, self.context.get('request'))


class LeagueSerializer(serializers.ModelSerializer):
    teams = TeamSerializer(many=True, read_only=True)
    logo = serializers.SerializerMethodField()

    class Meta:
        model = League
        fields = ['id', 'name', 'abbreviation', 'logo', 'teams']

    def get_logo(self, obj):
        return build_media_url(obj.logo, self.context.get('request'))
