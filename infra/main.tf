terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 3.83.0"
    }
  }
  backend "azurerm" {
    resource_group_name   = "terraform-cloud"
    storage_account_name  = "storageprojetocloud"
    container_name        = "tfstate"
    key                   = "terraform.tfstate"
  }
}

provider "azurerm" {
  skip_provider_registration = true
  features {
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
  }
}

provider "azuread" {}

data "azurerm_client_config" "current" {}

locals {
  location         = "northeurope"
  rg_name          = "terraform-cloud"
  vnet_name        = "cloudvnet"
  subnet_app_name  = "subnetappname"
  subnet_priv_name = "subnetprivname"
  cosmos_name      = "terraformcloudcosmosdb"
  webapp_name      = "reddit-app"
  funcapp_name     = "propjetocloudfunctionapp"
  plan_name        = "asp-project-cloud"
  storage_name     = "storageprojetocloud"
  translator_name  = "translator-service"
}

resource "azurerm_resource_group" "main" {
  name     = local.rg_name
  location = local.location
}

resource "azurerm_cognitive_account" "translator" {
  name                = local.translator_name
  location            = local.location
  resource_group_name = azurerm_resource_group.main.name
  kind                = "TextTranslation"
  sku_name            = "F0"
}

resource "azurerm_virtual_network" "main" {
  name                = local.vnet_name
  address_space       = ["10.10.0.0/16"]
  location            = local.location
  resource_group_name = azurerm_resource_group.main.name
}

resource "azurerm_subnet" "app" {
  name                 = local.subnet_app_name
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.10.1.0/24"]
  delegation {
    name = "appsvc"
    service_delegation {
      name    = "Microsoft.Web/serverFarms"
      actions = ["Microsoft.Network/virtualNetworks/subnets/action"]
    }
  }
}

resource "azurerm_subnet" "priv" {
  name                 = local.subnet_priv_name
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.10.2.0/24"]
}

resource "azurerm_public_ip" "nat" {
  name                = "nat-ip"
  location            = local.location
  resource_group_name = azurerm_resource_group.main.name
  allocation_method   = "Static"
  sku                 = "Standard"
}

resource "azurerm_nat_gateway" "main" {
  name                = "nat-gateway"
  location            = local.location
  resource_group_name = azurerm_resource_group.main.name
  sku_name            = "Standard"
}

resource "azurerm_nat_gateway_public_ip_association" "main" {
  nat_gateway_id       = azurerm_nat_gateway.main.id
  public_ip_address_id = azurerm_public_ip.nat.id
}

resource "azurerm_subnet_nat_gateway_association" "app" {
  subnet_id      = azurerm_subnet.app.id
  nat_gateway_id = azurerm_nat_gateway.main.id
}

resource "azurerm_cosmosdb_account" "main" {
  name                = local.cosmos_name
  location            = local.location
  resource_group_name = azurerm_resource_group.main.name
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"
  consistency_policy {
    consistency_level = "Session"
  }
  geo_location {
    location          = local.location
    failover_priority = 0
  }
  capabilities {
    name = "EnableServerless"
  }
}

resource "azurerm_cosmosdb_sql_database" "main" {
  name                = "RedditApp"
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
}

resource "azurerm_cosmosdb_sql_container" "main" {
  name                = "posts"
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
  database_name       = azurerm_cosmosdb_sql_database.main.name
  partition_key_paths = ["/id"]
}

resource "azurerm_service_plan" "main" {
  name                = local.plan_name
  location            = local.location
  resource_group_name = azurerm_resource_group.main.name
  os_type             = "Linux"
  sku_name            = "B2"
}

resource "azurerm_linux_web_app" "web" {
  name                = local.webapp_name
  resource_group_name = azurerm_resource_group.main.name
  location            = local.location
  service_plan_id     = azurerm_service_plan.main.id

  site_config {
    always_on        = true
    linux_fx_version = "DOCKER|rodrig0salv/minha-app:latest"
  }

  app_settings = {
    WEBSITES_ENABLE_APP_SERVICE_STORAGE = "false"
    DOCKER_REGISTRY_SERVER_URL          = "https://index.docker.io"
  }
}




resource "azurerm_app_service_virtual_network_swift_connection" "web" {
  app_service_id = azurerm_linux_web_app.web.id
  subnet_id      = azurerm_subnet.app.id
}

resource "azurerm_storage_account" "main" {
  name                     = local.storage_name
  resource_group_name      = azurerm_resource_group.main.name
  location                 = local.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_linux_function_app" "main" {
  name                       = local.funcapp_name
  location                   = local.location
  resource_group_name        = azurerm_resource_group.main.name
  service_plan_id            = azurerm_service_plan.main.id
  storage_account_name       = azurerm_storage_account.main.name
  storage_account_access_key = azurerm_storage_account.main.primary_access_key

  site_config {
    always_on = true
    application_insights_connection_string = "InstrumentationKey=41fe2caa-b77f-4aa5-8343-26999e3e615e"
    application_stack {
      python_version = "3.11"
    }
  }

  app_settings = {
    COSMOS_CONTAINER                     = azurerm_cosmosdb_sql_container.main.name
    COSMOS_DATABASE                      = azurerm_cosmosdb_sql_database.main.name
    COSMOS_ENDPOINT                      = azurerm_cosmosdb_account.main.endpoint
    COSMOS_KEY                           = azurerm_cosmosdb_account.main.primary_key
    DEPLOYMENT_STORAGE_CONNECTION_STRING = azurerm_storage_account.main.primary_connection_string
    REDDIT_PASSWORD                      = "miniprojetocloud"
    REDDIT_USER                          = "Major-Noise-6411"
    SECRET                               = "DoywW0Lcc26rvDforDKkLOSQsUUwYA"
    TRANSLATOR_ENDPOINT                  = azurerm_cognitive_account.translator.endpoint
    TRANSLATOR_KEY                       = azurerm_cognitive_account.translator.primary_access_key
    CLIENT_ID                            = data.azurerm_client_config.current.client_id
  }
}

resource "azurerm_app_service_virtual_network_swift_connection" "func" {
  app_service_id = azurerm_linux_function_app.main.id
  subnet_id      = azurerm_subnet.app.id
}

resource "azurerm_private_endpoint" "cosmos" {
  name                = "pe-cosmos"
  location            = local.location
  resource_group_name = azurerm_resource_group.main.name
  subnet_id           = azurerm_subnet.priv.id

  private_service_connection {
    name                           = "psc-cosmos"
    private_connection_resource_id = azurerm_cosmosdb_account.main.id
    subresource_names              = ["Sql"]
    is_manual_connection           = false
  }
}

output "functionapp_name" {
  value = azurerm_linux_function_app.main.name
}

output "functionapp_resource_group" {
  value = azurerm_resource_group.main.name
}

output "functionapp_publish_url" {
  value = azurerm_linux_function_app.main.default_hostname
}

output "functionapp_storage_account" {
  value = azurerm_storage_account.main.name
}

output "cosmosdb_endpoint" {
  value = azurerm_cosmosdb_account.main.endpoint
}

output "translator_endpoint" {
  value = azurerm_cognitive_account.translator.endpoint
}

output "translator_key" {
  value     = azurerm_cognitive_account.translator.primary_access_key
  sensitive = true
}

output "cosmosdb_key" {
  value     = azurerm_cosmosdb_account.main.primary_key
  sensitive = true
}

output "storage_connection_string" {
  value     = azurerm_storage_account.main.primary_connection_string
  sensitive = true
}
