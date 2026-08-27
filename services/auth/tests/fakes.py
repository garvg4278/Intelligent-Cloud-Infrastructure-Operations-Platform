class FakeAuditClient:
    def __init__(self, raise_error: bool = False):
        self.raise_error = raise_error
        self.calls: list[dict] = []

    def record(self, actor, action, resource_type, resource_id, before_state=None, after_state=None):
        if self.raise_error:
            from app.audit_client import AuditClientError

            raise AuditClientError("simulated audit service failure")
        self.calls.append(
            {
                "actor": actor,
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "before_state": before_state,
                "after_state": after_state,
            }
        )
