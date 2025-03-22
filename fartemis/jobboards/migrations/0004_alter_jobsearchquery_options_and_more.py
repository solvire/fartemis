# Generated by Django 5.1.7 on 2025-03-20 18:44

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("jobboards", "0003_remove_feeditem_jobboards_f_posted__224715_idx_and_more"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="jobsearchquery",
            options={
                "verbose_name": "Feed Fetch Log",
                "verbose_name_plural": "Feed Fetch Logs",
            },
        ),
        migrations.RemoveIndex(
            model_name="job",
            name="jobboards_j_user_id_8722f3_idx",
        ),
        migrations.RemoveIndex(
            model_name="job",
            name="jobboards_j_user_id_ea48a4_idx",
        ),
        migrations.AlterUniqueTogether(
            name="job",
            unique_together={("source", "source_id")},
        ),
        migrations.RemoveField(
            model_name="job",
            name="user",
        ),
    ]
