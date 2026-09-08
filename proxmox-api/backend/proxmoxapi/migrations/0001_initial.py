import django.db.models.deletion
import extensions.proxmoxapi.models
from django.db import migrations, models

SECTIONS = [
    {
        "name": "RESOURCES",
        "category": "Hardware",
        "templates": ["Proxmox QEMU VM", "Proxmox LXC Container"],
    },
    {
        "name": "NETWORKS",
        "category": "Networks",
        "templates": ["Proxmox QEMU VM", "Proxmox LXC Container"],
    },
    {
        "name": "QEMU_AGENT",
        "category": "Administrative data",
        "templates": ["Proxmox QEMU VM"],
    },
    {
        "name": "OPTIONS",
        "category": "Hardware",
        "templates": ["Proxmox QEMU VM", "Proxmox LXC Container"],
    },
    {
        "name": "SNAPSHOTS",
        "category": "Others",
        "templates": ["Proxmox QEMU VM", "Proxmox LXC Container"],
    },
    {
        "name": "BACKUPS",
        "category": "Others",
        "templates": ["Proxmox QEMU VM", "Proxmox LXC Container"],
    },
    {
        "name": "CLOUD_INIT",
        "category": "Networks",
        "templates": ["Proxmox QEMU VM"],
    },
]

SECTION_FIELDS = {
    "NETWORKS": [
        ("Identifier", "identifier"),
        ("Name",       "name"),
        ("Bridge",     "bridge"),
        ("Firewall",   "firewall"),
        ("Tag",        "tag"),
        ("MAC Address","hwaddr"),
        ("IPv4",       "ipv4"),
        ("IPv6",       "ipv6"),
        ("Gateway",    "gw"),
        ("MTU",        "mtu"),
        ("Link Down",  "link_down"),
    ],
    "RESOURCES": [
        ("Memory",    "mem"),
        ("Swap",      "swap"),
        ("Cores",     "cpus"),
        ("Root Disk", "disk"),
    ],
    "QEMU_AGENT": [
        ("Enabled", "enabled"),
        ("Type",    "type"),
    ],
    "OPTIONS": [
        ("Start at Boot", "onboot"),
        ("Protection",    "protection"),
        ("Startup Order", "startup"),
        ("Tags",          "tags"),
        ("Notes",         "notes"),
    ],
    "SNAPSHOTS": [
        ("Name",         "name"),
        ("Description",  "description"),
        ("Date",         "snaptime"),
        ("Includes RAM", "vmstate"),
        ("Parent",       "parent"),
    ],
    "BACKUPS": [
        ("Volume ID", "volid"),
        ("Storage",   "storage"),
        ("Size",      "size"),
        ("Format",    "format"),
        ("Date",      "ctime"),
        ("Notes",     "notes"),
    ],
    "CLOUD_INIT": [
        ("Type",          "citype"),
        ("User",          "ciuser"),
        ("DNS Server",    "nameserver"),
        ("Search Domain", "searchdomain"),
        ("IP Config",     "ipconfig"),
    ],
}

ALL_TEMPLATES = ["Proxmox QEMU VM", "Proxmox LXC Container"]


def create_templates(apps, _):
    Template = apps.get_model("template", "Template")
    Template.objects.get_or_create(
        name="Proxmox QEMU VM",
        defaults={"os": "VIRT", "is_protected": True},
    )
    Template.objects.get_or_create(
        name="Proxmox LXC Container",
        defaults={"os": "VIRT", "is_protected": True},
    )


def delete_templates(apps, _):
    Template = apps.get_model("template", "Template")
    Template.objects.filter(name__in=["Proxmox QEMU VM", "Proxmox LXC Container"]).delete()


def create_sections(apps, _):
    Template = apps.get_model("template", "Template")
    Section = apps.get_model("section", "Section")
    Category = apps.get_model("category", "Category")

    for section_def in SECTIONS:
        for template_name in section_def["templates"]:
            try:
                template = Template.objects.get(name=template_name)
            except Template.DoesNotExist:
                continue

            try:
                section, _ = Section.objects.get_or_create(
                    name=section_def["name"],
                    template=template,
                    defaults={
                        "retrieval_method": "FILE",
                        "retrieval_output": "JSON",
                        "target": "",
                        "options": None,
                    },
                )
                try:
                    category = Category.objects.get(name=section_def["category"])
                    category.inventory_sections.add(section)
                except Category.DoesNotExist:
                    pass
            except Exception as e:
                print(e)


def delete_sections(apps, _):
    Template = apps.get_model("template", "Template")
    Section = apps.get_model("section", "Section")

    section_names = [s["name"] for s in SECTIONS]
    templates = Template.objects.filter(
        name__in=["Proxmox QEMU VM", "Proxmox LXC Container"]
    )
    Section.objects.filter(name__in=section_names, template__in=templates).delete()


def create_fields(apps, _):
    Template = apps.get_model("template", "Template")
    Section = apps.get_model("section", "Section")
    Field = apps.get_model("field", "Field")

    for template_name in ALL_TEMPLATES:
        try:
            template = Template.objects.get(name=template_name)
        except Template.DoesNotExist:
            continue

        for section_name, fields in SECTION_FIELDS.items():
            try:
                section = Section.objects.get(name=section_name, template=template)
            except Section.DoesNotExist:
                continue

            for order, (field_name, retrieval_value) in enumerate(fields, start=1):
                Field.objects.get_or_create(
                    name=field_name,
                    section=section,
                    defaults={
                        "retrieval_value": retrieval_value,
                        "order": order,
                        "options": None,
                    },
                )


def delete_fields(apps, _):
    Template = apps.get_model("template", "Template")
    Section = apps.get_model("section", "Section")
    Field = apps.get_model("field", "Field")

    templates = Template.objects.filter(name__in=ALL_TEMPLATES)
    sections = Section.objects.filter(
        name__in=list(SECTION_FIELDS.keys()), template__in=templates
    )
    Field.objects.filter(section__in=sections).delete()


def create_scheduler_entry(apps, _):
    Scheduler = apps.get_model("scheduler", "Scheduler")
    Scheduler.objects.get_or_create(
        name="proxmoxInventory.ProxmoxInventory",
        defaults={
            "description": "Proxmox VE inventory synchronization",
            "active": True,
            "recurrence": "daily",
            "last_execution": None,
            "hour": "02:00",
            "day_of_week": None,
            "day_of_month": None,
            "is_protected": True,
        },
    )


def delete_scheduler_entry(apps, _):
    Scheduler = apps.get_model("scheduler", "Scheduler")
    Scheduler.objects.filter(name="proxmoxInventory.ProxmoxInventory").delete()


def create_proxmox_assignment_rules(apps, schema_editor):
    Rule = apps.get_model("rule", "Rule")
    Action = apps.get_model("rule", "Action")
    Template = apps.get_model("template", "Template")

    lxc_template = Template.objects.filter(name="Proxmox LXC Container").first()
    qemu_template = Template.objects.filter(name="Proxmox QEMU VM").first()

    # Run after every pre-existing "inventory_received" rule: priority is
    # execution order (lowest runs first), so append at the end of the list.
    max_priority = Rule.objects.filter(trigger="inventory_received").aggregate(
        models.Max("priority")
    )["priority__max"] or 0

    rules = [
        {
            "description": "Assign Proxmox LXC Container template",
            "trigger": "inventory_received",
            "enabled": True,
            "logic": {"==": [{"var": "proxmox.resource_type"}, "lxc"]},
            "priority": max_priority + 1,
            "template": lxc_template,
        },
        {
            "description": "Assign Proxmox QEMU VM template",
            "trigger": "inventory_received",
            "enabled": True,
            "logic": {"==": [{"var": "proxmox.resource_type"}, "qemu"]},
            "priority": max_priority + 2,
            "template": qemu_template,
        },
    ]

    for rule in rules:
        template = rule.pop("template")
        if template is None:
            continue
        try:
            new_rule = Rule.objects.create(
                break_on_match=False,
                **rule,
            )
            Action.objects.create(
                rule=new_rule,
                action="set",
                field="template",
                value=template.id,
                priority=1,
            )
        except Exception as e:
            print(e)


def delete_proxmox_assignment_rules(apps, schema_editor):
    Rule = apps.get_model("rule", "Rule")
    Rule.objects.filter(
        trigger="inventory_received",
        description__in=[
            "Assign Proxmox LXC Container template",
            "Assign Proxmox QEMU VM template",
        ],
    ).delete()


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('inventory_base', '0001_initial'),
        ('template', '0001_initial'),
        ('section', '0009_alter_section_template'),
        ('category', '0001_initial'),
        ('field', '0009_alter_field_options_alter_field_retrieval_value_and_more'),
        ('scheduler', '0001_initial'),
        ('rule', '0002_alter_action_options_alter_rule_options'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProxmoxServer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, unique=True)),
                ('description', models.CharField(blank=True, default='', max_length=255)),
                ('ip_address', models.CharField(max_length=255, validators=[extensions.proxmoxapi.models.validate_hostname_or_ip])),
                ('port', models.IntegerField(default=8006)),
                ('node_names', models.JSONField(default=list)),
                ('username', models.CharField(max_length=255)),
                ('token_id', models.CharField(max_length=255)),
                ('token_secret', models.CharField(max_length=512)),
                ('request_delay', models.FloatField(default=3000)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['-updated_at'],
            },
        ),
        migrations.CreateModel(
            name='ProxmoxAsset',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('vmid', models.IntegerField()),
                ('resource_type', models.CharField(choices=[('qemu', 'QEMU VM'), ('lxc', 'LXC Container')], max_length=10)),
                ('status', models.CharField(blank=True, max_length=50)),
                ('last_update', models.DateTimeField(auto_now=True)),
                ('asset', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='proxmox_asset', to='inventory_base.inventorybase')),
                ('server', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='proxmox_assets', to='proxmoxapi.proxmoxserver')),
            ],
            options={
                'ordering': ['server', 'resource_type', 'vmid'],
                'unique_together': {('server', 'vmid', 'resource_type')},
            },
        ),
        migrations.RunPython(create_templates, delete_templates),
        migrations.RunPython(create_sections, delete_sections),
        migrations.RunPython(create_fields, delete_fields),
        migrations.RunPython(create_scheduler_entry, delete_scheduler_entry),
        migrations.RunPython(
            create_proxmox_assignment_rules,
            delete_proxmox_assignment_rules,
        ),
    ]
