import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='TweetNode',
            fields=[
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('title', models.CharField(max_length=25)),
                ('content', models.TextField(max_length=280)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('number_of_likes', models.PositiveIntegerField(default=0)),
                ('number_of_retweets', models.PositiveIntegerField(default=0)),
                ('is_retweet', models.BooleanField(default=False)),
                ('liked_by', models.ManyToManyField(blank=True, related_name='liked_tweets', to='users.userprofile')),
                ('original_tweet', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='retweets', to='tweets.tweetnode')),
                ('parent_node', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='replies', to='tweets.tweetnode')),
                ('retweeted_by', models.ManyToManyField(blank=True, related_name='retweeted_tweets', to='users.userprofile')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tweets', to='users.userprofile')),
            ],
            options={
                'verbose_name': 'Tweet Node',
                'verbose_name_plural': 'Tweet Nodes',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='EmbeddingReference',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('pinecone_vector_id', models.CharField(max_length=255, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('tweet', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='embedding_ref', to='tweets.tweetnode')),
            ],
            options={
                'verbose_name': 'Embedding Reference',
                'verbose_name_plural': 'Embedding References',
            },
        ),
    ]
