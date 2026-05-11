from __future__ import annotations

import json

from django import forms

from apps.scanners.models import Scanner


def _default_schema_text() -> str:
    return json.dumps(
        {
            "fields": [
                {
                    "kind": "field",
                    "name": "example_field",
                    "label": "Example Field",
                    "data_type": "string",
                    "required": True,
                    "description": "Replace with a real field.",
                    "options": {},
                }
            ]
        },
        indent=2,
    )


class ScannerForm(forms.ModelForm):
    schema_json_text = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 18, "spellcheck": "false"}),
        label="Field schema (JSON)",
        required=False,
    )

    class Meta:
        model = Scanner
        fields = [
            "name",
            "description",
            "priming_prompt",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
            "priming_prompt": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.schema_json:
            self.initial["schema_json_text"] = json.dumps(
                self.instance.schema_json, indent=2
            )
        elif not self.is_bound:
            self.initial["schema_json_text"] = _default_schema_text()

    def clean_schema_json_text(self) -> dict:
        text = self.cleaned_data.get("schema_json_text") or "{}"
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError(f"Schema JSON parse error: {exc}") from exc
        if not isinstance(data, dict) or "fields" not in data:
            raise forms.ValidationError("Schema must be a JSON object with a top-level 'fields' list.")
        if not isinstance(data["fields"], list):
            raise forms.ValidationError("'fields' must be a list.")
        return data


class ScanUploadForm(forms.Form):
    file = forms.FileField()


class ApiKeyForm(forms.Form):
    name = forms.CharField(max_length=80)
