# nomad job stop --namespace=* -purge fastapi-sample
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

variable "tls_domain" {
type = string
default = "fastapi-sample.service.gra.dev.consul" # service.gra.dev.consul
}

variable "alt_names" {
type = string
default = ""
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
      min_healthy_time  = "5s"
      healthy_deadline  = "5m"
      progress_deadline = "0"
      canary            = 0
      auto_revert       = var.env == "prod" ? true : false
      auto_promote      = var.env == "prod" ? true : false
    }

    restart {
      attempts = 3
      interval = "5m"
      delay = "25s"
      mode     = var.env == "dev" ? "fail" : "delay"
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
        SENTRY_RELEASE = "[[ .CI_COMMIT_TAG ]]"
        DD_VERSION = "[[ .CI_COMMIT_TAG ]]"
        DD_GIT_COMMIT_SHA = "[[ .CI_COMMIT_SHA ]]"
        DD_GIT_REPOSITORY_URL = "git@gitlab.com:jusmundi-group/proof-of-concept/fastapi-sample.git"
        DD_TRACE_SAMPLING_RULES = "[{\"service\":\"fastapi-sample\",\"resource\":\"GET /metrics\",\"sample_rate\":0.01},{\"service\":\"fastapi-sample\",\"resource\":\"GET /health\",\"sample_rate\":0.01},{\"service\":\"fastapi-sample\",\"resource\":\"GET /v1/ping\",\"sample_rate\":0.01},{\"service\":\"fastapi-sample\",\"resource\":\"GET /v2/ping\",\"sample_rate\":0.01},{\"service\":\"fastapi-sample\",\"resource\":\"GET /ping\",\"sample_rate\":0.01},{\"service\":\"fastapi-sample\",\"resource\":\"GET /cpu_task\",\"sample_rate\":1},{\"service\":\"fastapi-sample\",\"resource\":\"POST /io_task\",\"sample_rate\":1}]"
      }

      vault {
        policies  = ["cicd", "default"]
      }

# below was working
/*
      template {
        data        = <<EOF
{{ with pkiCert "pki_int/issue/example-dot-com" "common_name=fastapi-sample.service.gra.dev.consul" }}
{{ .Cert }}{{ .CA }}{{ .Key }}
{{ end }}
EOF
        destination = "local/test.pem"

        # destination   = "${NOMAD_SECRETS_DIR}/bundle.pem"
        change_mode   = "restart"
      }
*/

#  error calling writeToFile: function is disabled
/*
      template {
        data        = <<EOF
{{ with pkiCert "pki_int/issue/example-dot-com" "common_name=fastapi-sample.service.gra.dev.consul" }}
{{ .Cert }}{{ .CA }}{{ .Key }}
{{ .Key | writeToFile "examples/my-app.key" "root" "root" "0400" }}
{{ .CA | writeToFile "examples/ca.crt" "root" "root" "0644" }}
{{ .Cert | writeToFile "examples/my-app.crt" "root" "root" "0644" "append" }}
{{ end }}
EOF
        destination = "local/test.pem"

        # destination   = "${NOMAD_SECRETS_DIR}/bundle.pem"
        change_mode   = "restart"
      }
*/

# https://support.hashicorp.com/hc/en-us/articles/15712419079315-Templates-Using-nomad-attributes-when-creating-PKI-certificates-with-Vault
# {{ with secret "pki/issuer/d4d8fe33-4446-ea83-ff48-47832a7e6784/issue/test-example-dot-com" "common_name=fastapi-sample.service.gra.dev.consul" "ip_sans=127.0.0.1" "format=pem" }}
# write pki_int/issue/example-dot-com common_name=fastapi-sample.service.gra.dev.consul
# See https://github.com/hashicorp/nomad/issues/19380

/*
      template {
data = <<EOF
{{ with secret "pki_int/issue/example-dot-com" "common_name=fastapi-sample.service.gra.dev.consul" }}
{{ .Data.certificate }}
{{ .Data.issuing_ca }}
{{ .Data.private_key }}{{ end }}
EOF
       # destination   = "${NOMAD_SECRETS_DIR}/bundle.pem"
       destination   = "local/bundle.pem"
       change_mode   = "restart"
     }
*/

/*
template {
data = <<EOH
{{- $VAR1 := (printf "ip_sans=%s" (env "attr.unique.network.ip-address")) -}}
{{- with secret "pki_int/issue/test-example-dot-com" "common_name=${var.tls_domain}" "alt_names=${var.alt_names}" $VAR1 -}}
{{- .Data.certificate -}}
{{- printf "\n" -}}
{{- .Data.issuing_ca -}}
{{ end }}

EOH
destination = "local/bundle.pem"
change_mode = "restart"
}
*/

# vault write pki_int/issue/example-dot-com common_name="fastapi-sample.service.gra.dev.consul" ttl="24h"
/*
template {
  error_on_missing_key = true

  data = <<EOH
  {{- $VAR1 := (printf "ip_sans=%s" (env "attr.unique.network.ip-address")) -}}
  {{- with pkiCert "pki_int/issue/example-dot-com" "common_name=${var.tls_domain}" "alt_names=${var.alt_names}" $VAR1 -}}
  {{- .Cert -}}
  {{- printf "\n" -}}
  {{- .CA -}}
  {{ end }}

  EOH
  destination = "local/bundle2.pem"
  change_mode = "restart"
}
*/

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
{{ with secret "datascience/test/fastapi-sample" }}
{{.Data.data.ENV}}
{{ end }}
EOF
          destination = "secrets/env.authheader"
          env = true
      }

      service {
        name = "fastapi-sample"
        port = "server"

        tags = [
          "api",
          "traefik.enable=true",
          "traefik.http.routers.fastapi-sample.entrypoints=https",
          "traefik.http.routers.fastapi-sample.rule=Host(`fastapi-sample.service.gra.${var.env}.consul`)",
          "traefik.http.routers.fastapi-sample.tls=true",
          "traefik.http.routers.fastapi-sample.tls.options=myTLS12@file",
          "traefik.http.middlewares.redirect-https.redirectScheme.scheme=https",
          "traefik.http.middlewares.redirect-https.redirectScheme.permanent=true",
          # my-traefik-real-ip@file redirect-https
          "traefik.http.routers.fastapi-sample.middlewares=my-plugindemo@file,test-ratelimit@consulcatalog,test-inflightreq@consulcatalog",
          # 403 "traefik.http.routers.fastapi-sample.middlewares=my-crowdsec-bouncer-traefik-plugin@file",
          # "traefik.http.routers.fastapi-sample.middlewares=my-plugindemo@file,my-traefik-real-ip@file,my-crowdsec-bouncer-traefik-plugin@file,my-traefik-jwt-plugin@file",
          # test-ratelimit@consulcatalog,test-inflightreq@consulcatalog
          "traefik.http.middlewares.crowdsec.plugin.bouncer.forwardedheaderstrustedips=10.30.10.254,145.239.211.190,82.66.4.247", # LAN
          "traefik.http.middlewares.crowdsec.plugin.bouncer.clientTrustedips=10.30.0.115/32,10.20.0.115/32,10.10.0.126/32",
          #
          "traefik.http.middlewares.test-ratelimit.ratelimit.average=100",
          # "traefik.http.middlewares.test-ratelimit.ratelimit.period=1s"
          "traefik.http.middlewares.test-ratelimit.ratelimit.burst=50",
          "traefik.http.middlewares.test-inflightreq.inflightreq.amount=10",
          "traefik.http.middlewares.test-inflightreq.inflightreq.sourcecriterion.ipstrategy.excludedips=127.0.0.1/32,192.168.1.7,10.30.0.115/32,10.20.0.115/32,10.10.0.126/32",
          "traefik.http.services.fastapi-sample.loadbalancer.server.scheme=http",
          "traefik.http.services.fastapi-sample.loadbalancer.healthCheck.path=/health",
          "traefik.http.services.fastapi-sample.loadbalancer.healthCheck.interval=10s",
          "traefik.http.services.fastapi-sample.loadbalancer.healthCheck.timeout=3s",
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
            // "nabla/perf/locustfile.py",
            "nabla/perf/locustfile_jm.py",
            //"--master",
            //"-H",
            //"http://fastapi-sample-locust.service.gra.${var.env}.consul:8089",
            //"--env targetHost="https://jm-ksdifu78gwc45gv1s0jshgtr764jnb79.lexsportiva.tech/en",
            //"--headless",
            "--autostart",
            "--host",
            "http://0.0.0.0:8091/v1/internal-api",
            "--users",
            "5",
            // "-c","1000",
            // "-r","100",
            "--processes","4",
            "--run-time","1h30m",
        ]

        # shm_size = 536870912 # 512MB
      }

      vault {
        policies  = ["cicd"]
      }

      service {
        name = "fastapi-sample-locust"
        port = "locust"

        tags = [
          "traefik.enable=true",
          "traefik.http.routers.fastapi-sample-locust.entrypoints=http",
          "traefik.http.routers.fastapi-sample-locust.rule=Host(`fastapi-sample-locust.service.gra.${var.env}.consul`)",
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

  } # group fastapi-sample

}
