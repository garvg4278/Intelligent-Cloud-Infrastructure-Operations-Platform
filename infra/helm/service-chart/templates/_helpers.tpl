{{- define "service-chart.fullname" -}}
{{- .Release.Name -}}
{{- end -}}

{{- define "service-chart.labels" -}}
app.kubernetes.io/name: {{ .Release.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end -}}

{{- define "service-chart.selectorLabels" -}}
app.kubernetes.io/name: {{ .Release.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "service-chart.podLabels" -}}
{{ include "service-chart.selectorLabels" . }}
icop.io/component: {{ .Values.component | default "backend-service" }}
{{- end -}}

{{- define "service-chart.serviceAccountName" -}}
{{- if .Values.serviceAccount.name -}}
{{- .Values.serviceAccount.name -}}
{{- else if .Values.serviceAccount.create -}}
{{- include "service-chart.fullname" . -}}
{{- else -}}
default
{{- end -}}
{{- end -}}
