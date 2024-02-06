# nomad job run -var env=uat -var team=uat job.nomad

variable "env" {
  type    = string
  default = "dev"

  validation {
    condition     = var.env == "dev" || var.env == "uat" || var.env == "prod"
    error_message = "The env value must be valid env uat or prod."
  }
}

variable "team" {
  type    = string
  default = "uat"

  validation {
    condition     = var.team == "ateam" || var.team == "bteam" || var.team == "uat" || var.team == "prod" || var.team == "dev"
    error_message = "The env value must be valid team ateam or bteam."
  }
}

variable "datacenters" {
  type        = list(string)
  description = "List of datacenters to deploy to."
  default     = ["gra"]
}

job "fastapi-sample" {
  datacenters = var.datacenters
  namespace   = "datascience"
  type        = "service"

  # Meta keys are also interpretable.
  meta {
    version  = "v0.0.1"
    region   = "${node.region}"
    dc       = "${node.datacenter}"
    scope    = "test"
    service  = "fastapi-sample-${var.env}"
    team     = "${var.team}"
    env      = "${var.env}"
  }

  group "fastapi-sample" {
    count = 1

    scaling {
      min     = 1
      max     = 4
      enabled = true

      policy {
        evaluation_interval = "2s"
        cooldown            = "2s"

        // check "active_connections" {
        //   source = "prometheus"
        //   query  = "nomad_client_allocs_cpu_total_percent{task='loki-${var.team}'}"

        //   strategy "target-value" {
        //     target = 70
        //   }
        // }
      }
    } # scaling

    ephemeral_disk {
      # Used to store index, cache, WAL
      # Nomad will try to preserve the disk between job updates
       size   = 500
       sticky  = true
       # migrate = true
    }

    # Canary disable, because service is too big 10 G minimum and cluster is not sized for it, so auto_promote set to false
    update {
      max_parallel      = 1
      canary            = 0
      min_healthy_time  = "10m"
      healthy_deadline  = "30m"
      progress_deadline = 0
      auto_revert       = true
      auto_promote      = false
    }

    network {
      port "server" {
        to     = 8080
      }

      port "locust" {
        to     = 8089
        static = 8089
      }

      port "locust-exporter" {
        to     = 9646
        # static = 9646
      }
    }

    restart {
      interval = "5m"
      attempts = 3
      delay    = "15s"
      mode     = "fail"
    }

    // volume "nabla" {
    //   type            = "csi"
    //   source          = "juicefs-gra-nabla-${var.env}"
    //   attachment_mode = "file-system"
    //   access_mode     = "multi-node-multi-writer"
    // }

    task "fastapi-sample" {
      driver = "docker"

      config {
        image = "[[ .CONTAINER_IMAGE ]]"
        ports = ["server"]

        # force_pull = true
        shm_size = 536870912 # 512MB
        auth_soft_fail = true
        # image_pull_timeout = "25m"

        memory_hard_limit = 2048  # at ???G we will have OOM and the container will be killed
      }

      env {
        FASTAPI_ENV = "development"
      }

      vault {
        policies  = ["cicd"]
      }

      template {
        data        = <<EOF
UVICORN_LOG_LEVEL=debug
OTEL_RESOURCE_ATTRIBUTES=service.name=fastapi-sample
OTEL_SERVICE_NAME=fastapi-sample
OTEL_EXPORTER_OTLP_ENDPOINT="http://otel-collector.service.gra.${var.env}.consul:4317"
PYROSCOPE_ENDPOINT="http://pyroscope.service.gra.${var.env}.consul"
EOF
        destination = "${NOMAD_SECRETS_DIR}/.env.local"

        env         = true
      }

      template {
          change_mode = "noop"

          data = <<EOF
{{ with secret "infrastructure/elasticsearch-vars" }}
AuthHeader = {{ printf "%s:%s" .Data.data.ELASTICSEARCH_USER .Data.data.ELASTICSEARCH_PASSWORD | base64URLEncode }}
{{ end }}
EOF
          destination = "secrets/env.authheader"
          env = true
      }

      service {
        name = "fastapi-sample"
        port = "server"

        tags = [
          "traefik.enable=true",
          "traefik.http.routers.fastapi-sample.entrypoints=https",
          // "traefik.http.routers.fastapi-sample.rule=Host(`fastapi-sample.service.gra.${var.env}.consul`)",
          var.env == "uat" ? "traefik.http.routers.fastapi-sample.rule=Host(`fastapi-sample.staging.int.jusmundi.com`) || Host(`fastapi-sample.service.gra.${var.env}.consul`)" : "traefik.http.routers.fastapi-sample.rule=Host(`fastapi-sample.${var.env}.int.jusmundi.com`) || Host(`fastapi-sample.service.gra.${var.env}.consul`)",
          "traefik.http.routers.fastapi-sample.tls=true",
          "traefik.http.routers.fastapi-sample.middlewares=my-traefik-real-ip@file,my-crowdsec-bouncer-traefik-plugin@file,my-traefik-jwt-plugin@file",
          # "traefik.http.routers.fastapi-sample.middlewares=my-plugindemo@file,my-traefik-real-ip@file,my-crowdsec-bouncer-traefik-plugin@file,my-traefik-jwt-plugin@file",
          # ,test-ratelimit@consulcatalog,test-inflightreq@consulcatalog
          "traefik.http.middlewares.crowdsec.plugin.bouncer.forwardedheaderstrustedips=10.30.10.254,145.239.211.190,82.66.4.247", # LAN
          "traefik.http.middlewares.crowdsec.plugin.bouncer.clientTrustedips=10.30.0.115/32,10.20.0.115/32,10.10.0.126/32",
          #
          "traefik.http.middlewares.test-ratelimit.ratelimit.average=100",
          # "traefik.http.middlewares.test-ratelimit.ratelimit.period=1s"
          "traefik.http.middlewares.test-ratelimit.ratelimit.burst=50",
          "traefik.http.middlewares.test-inflightreq.inflightreq.amount=10",
          "traefik.http.middlewares.test-inflightreq.inflightreq.sourcecriterion.ipstrategy.excludedips=127.0.0.1/32,192.168.1.7,10.30.0.115/32,10.20.0.115/32,10.10.0.126/32"
        ]

        check {
          name     = "server-alive"
          port     = "server"
          type     = "http"
          path     = "/health" # v1/ping /docs /metrics
          # 30s because can be heavy to lead, better to put it at this interval
          interval = "30s"
          timeout  = "5s"

          # header {
          #   Authorization = ["Basic ${AuthHeader}"]
          # }
        }

      } # service fastapi-sample

      resources {
        cpu    = 200 # MHz
        memory = 100 # MB
      }
    } # task fastapi-sample

    task "fastapi-sample-locust" {
      driver = "docker"
      config {
        image = "[[ .CONTAINER_IMAGE ]]"
        # image = "locustio/locust"

        image_pull_timeout = "25m"
        ports = ["locust"]

        command = "python"
        args = [
            "/code/.venv/bin/locust",
            "-f",
            "nabla/perf/locustfile_jm.py",
            //"--master",
            //"-H",
            //"http://fastapi-sample-locust.service.gra.${var.env}.consul:8089",
            //"--env targetHost="https://jm-ksdifu78gwc45gv1s0jshgtr764jnb79.lexsportiva.tech/en",
        ]

        # shm_size = 536870912 # 512MB
      }

      env {
        targetHost = "https://jm-ksdifu78gwc45gv1s0jshgtr764jnb79.lexsportiva.tech/en"
        FASTAPI_ENV = "production"
      }

      vault {
        policies  = ["cicd"]
      }

/*
      template {
        data        = <<EOF
TEMPORALIO_HOST="temporal-app.service.gra.dev.consul"
UVICORN_LOG_LEVEL=debug
EOF
        destination = "${NOMAD_SECRETS_DIR}/.env.local"

        env         = true
      }
*/
      service {
        name = "fastapi-sample-locust"
        port = "locust"

        tags = [
          "traefik.enable=true",
          "traefik.http.routers.fastapi-sample-locust.entrypoints=http",
          // "traefik.http.routers.fastapi-sample-locust.rule=Host(`fastapi-sample-locust.service.gra.${var.env}.consul`)",
          var.env == "uat" ? "traefik.http.routers.fastapi-sample-locust.rule=Host(`fastapi-sample-locust.staging.int.jusmundi.com`) || Host(`fastapi-sample-locust.service.gra.${var.env}.consul`)" : "traefik.http.routers.fastapi-sample-locust.rule=Host(`fastapi-sample-locust.${var.env}.int.jusmundi.com`) || Host(`fastapi-sample-locust.service.gra.${var.env}.consul`)",
        ]

        # check {
        #   name     = "server-prometheus"
        #   port     = "locust"
        #   type     = "http"
        #   path     = "/metrics"
        #   interval = "5m"
        #   timeout  = "20m"
        # }

      } # service locust

      resources {
        cpu    = var.env == "dev" ? "100" : "200" # MHz
        memory = var.env == "dev" ? "400" : "500" # MB 5Gb minimum
      }
    } # task fastapi-sample-locust

    task "fastapi-sample-locust-exporter" {
      driver = "docker"
      config {
        image = "containersol/locust_exporter"
        image_pull_timeout = "25m"
        ports = ["locust-exporter"]
        # force_pull = true

        # network_mode = "host"

        # command = "python"
        #args = [
        #     "--locust.uri",
        #    "http://fastapi-sample-locust.service.gra.${var.env}.consul:8089",
        #]


        # shm_size = 536870912 # 512MB
      }

      vault {
        policies  = ["cicd"]
      }

      env {
        LOCUST_EXPORTER_URI = "http://fastapi-sample-locust.service.gra.${var.env}.consul:8089"
      }
/*
      template {
        data        = <<EOF
TEMPORALIO_HOST="temporal-app.service.gra.dev.consul"
UVICORN_LOG_LEVEL=debug
EOF
        destination = "${NOMAD_SECRETS_DIR}/.env.local"

        env         = true
      }
*/
      service {
        name = "fastapi-sample-locust-exporter"
        port = "locust-exporter"

        tags = [
          "traefik.enable=true",
          "traefik.http.routers.fastapi-sample-locust-exporter.entrypoints=http",
          "traefik.http.routers.fastapi-sample-locust-exporter.rule=Host(`fastapi-sample-locust-exporter.service.gra.${var.env}.consul`)",
        ]

        # check {
        #   name     = "server-prometheus"
        #   port     = "locust-exporter"
        #   type     = "http"
        #   path     = "/metrics"
        #   interval = "5m"
        #   timeout  = "20m"
        # }

      } # service locust-exporter

      resources {
        cpu    = var.env == "dev" ? "100" : "200" # MHz
        memory = var.env == "dev" ? "400" : "500" # MB 5Gb minimum
      }
    } # task fastapi-sample-locust-exporter

    task "fastapi-sample-kong-registration" {

      driver = "docker"

      lifecycle {
        hook = "poststart"
      }

      config {
        image = "docker.io/kong/deck:v1.19.1"

        volumes = [
          "local/kong.yml:/kong.yml"
        ]

        image_pull_timeout = "10m"

        args = [
          "--kong-addr",
          "http://kong-admin.service.gra.${var.env}.consul",
          "sync",
          "--state",
          "/kong.yml",
          "--select-tag",
          "fastapi-sample"
        ]
      }

      template {
        destination = "local/kong.yml"

        data = <<EOF
_format_version: "3.0"
_info:
  select_tags:
  - fastapi-sample
services:
- connect_timeout: 60000
  host: fastapi-sample.service.gra.${var.env}.consul
  name: fastapi-sample
  path: /
  port: 80
  protocol: http
  read_timeout: 60000
  retries: 5
  routes:
  - hosts:
    %{ if var.env == "uat" }
    - fastapi-sample.staging.int.jusmundi.com
    %{ endif }
    - fastapi-sample.${var.env}.int.jusmundi.com
    https_redirect_status_code: 426
    methods:
    - GET
    - PUT
    - POST
    - DELETE
    name: fastapi-sample
    path_handling: v0
    preserve_host: false
    protocols:
    - http
    - https
    regex_priority: 0
    request_buffering: true
    response_buffering: true
    strip_path: true
  tags:
  - fastapi-sample
  write_timeout: 60000
EOF
      }

      resources {
        cpu    = 300 # Mhz
        memory = 300 # MB
      }

    } # task kong-registration

#    task "fastapi-sample-kong-disable" {
#
#      driver = "docker"
#
#      lifecycle {
#        hook = "poststop"
#      }
#
#      config {
#        image = "docker.io/kong/deck:v1.19.1"
#
#        volumes = [
#          "local/kong.yml:/kong.yml"
#        ]
#
#        image_pull_timeout = "10m"
#
#        args = [
#          "--kong-addr",
#          "http://kong-admin.service.gra.${var.env}.consul",
#          "sync",
#          "--state",
#          "/kong.yml",
#          "--select-tag",
#          "fastapi-sample"
#        ]
#      }
#
#      template {
#        destination = "local/kong.yml"
#
#        data = <<EOF
#_format_version: "3.0"
#_info:
#  select_tags:
#  - fastapi-sample
#services:
#- name: fastapi-sample
#  enabled: false
#  host: fastapi-sample.service.gra.${var.env}.consul
#EOF
#      }
#
#      resources {
#        cpu    = 300 # Mhz
#        memory = 300 # MB
#      }
#
#    } # task kong-disable

  } # group fastapi-sample

}
