from django.db import models

from ocsinventory_backend.ocs_framework.crypto import decrypt, encrypt


class ADDomain(models.Model):
    """One configured Active Directory domain, read over LDAP."""

    SECURITY_CHOICES = (
        ("none", "None"),
        ("starttls", "StartTLS"),
        ("ldaps", "LDAPS"),
    )

    name = models.CharField(max_length=255, unique=True)
    server = models.CharField(max_length=255)
    port = models.PositiveIntegerField(default=636)
    security = models.CharField(
        max_length=10, choices=SECURITY_CHOICES, default="ldaps"
    )
    verify_certificate = models.BooleanField(default=True)
    bind_dn = models.CharField(max_length=255)
    # Stored encrypted (see from_db()/save() below), never returned by the API.
    bind_password = models.CharField(max_length=512)
    base_dn = models.CharField(max_length=255)
    assigned_user_attribute = models.CharField(max_length=255, default="managedBy")
    is_active = models.BooleanField(default=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_sync_status = models.CharField(max_length=20, blank=True, default="")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        if "bind_password" in field_names:
            instance.bind_password = decrypt(instance.bind_password)
        return instance

    def save(self, *args, **kwargs):
        clear_password = self.bind_password
        self.bind_password = encrypt(self.bind_password)
        try:
            super().save(*args, **kwargs)
        finally:
            self.bind_password = clear_password


class ADComputer(models.Model):
    """
    One computer object read from a domain's directory.

    Rows only ever come from a sync: no create/update/delete through the API.
    """

    MATCH_STATUS_CHOICES = (
        ("linked", "Linked"),
        ("unlinked", "Unlinked"),
        ("ambiguous", "Ambiguous"),
    )
    LINK_MODE_CHOICES = (
        ("auto", "Automatic"),
        ("manual", "Manual"),
    )

    domain = models.ForeignKey(
        ADDomain, on_delete=models.CASCADE, related_name="computers"
    )
    object_guid = models.CharField(max_length=64)
    name = models.CharField(max_length=255)
    dns_hostname = models.CharField(max_length=255, blank=True, default="")
    distinguished_name = models.CharField(max_length=1024)
    ou = models.CharField(max_length=1024, blank=True, default="")
    ou_path = models.CharField(max_length=1024, blank=True, default="")
    os_name = models.CharField(max_length=255, blank=True, default="")
    os_version = models.CharField(max_length=255, blank=True, default="")
    enabled = models.BooleanField(default=True)
    description = models.CharField(max_length=1024, blank=True, default="")
    when_created = models.DateTimeField(null=True, blank=True)
    last_logon = models.DateTimeField(null=True, blank=True)
    password_last_set = models.DateTimeField(null=True, blank=True)

    # Assigned user, resolved from the domain's configurable attribute (e.g. managedBy).
    assigned_user_raw = models.CharField(max_length=1024, blank=True, default="")
    assigned_user_name = models.CharField(max_length=255, blank=True, default="")
    assigned_user_login = models.CharField(max_length=255, blank=True, default="")
    assigned_user_email = models.CharField(max_length=255, blank=True, default="")

    asset = models.OneToOneField(
        "inventory_base.InventoryBase",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ad_computer",
    )
    link_mode = models.CharField(
        max_length=10, choices=LINK_MODE_CHOICES, blank=True, default=""
    )
    match_status = models.CharField(
        max_length=10, choices=MATCH_STATUS_CHOICES, default="unlinked"
    )

    # False once the object is no longer returned by the directory, kept for history.
    in_directory = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["domain", "name"]
        unique_together = [("domain", "object_guid")]

    def __str__(self):
        return f"{self.name} ({self.domain.name})"


class SyncReport(models.Model):
    """Result of one synchronization run for one domain."""

    STATUS_CHOICES = (
        ("running", "Running"),
        ("success", "Success"),
        ("error", "Error"),
    )

    domain = models.ForeignKey(
        ADDomain, on_delete=models.CASCADE, related_name="reports"
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="running")
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    linked_count = models.PositiveIntegerField(default=0)
    missing_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.domain.name} - {self.started_at:%Y-%m-%d %H:%M:%S} ({self.status})"
