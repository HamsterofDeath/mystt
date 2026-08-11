#Requires -RunAsAdministrator
[CmdletBinding(SupportsShouldProcess)]
param()

$names = @(
    'JIRA_API_TOKEN',
    'JIRA_EMAIL',
    'JIRA_SITE_URL',
    'JIRA_CLOUD_ID',
    'JIRA_API_BASE_URL',
    'JIRA_PROJECT_KEY'
)

foreach ($name in $names) {
    $value = [Environment]::GetEnvironmentVariable($name, 'User')
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "The Windows user environment variable $name is missing."
    }
    if ($PSCmdlet.ShouldProcess("Machine environment", "Set $name")) {
        [Environment]::SetEnvironmentVariable($name, $value, 'Machine')
    }
}

Write-Host 'Installed Jira configuration in the Windows machine environment. Restart terminals and apps to inherit it.'
