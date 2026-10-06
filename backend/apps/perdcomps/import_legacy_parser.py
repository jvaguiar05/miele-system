"""PER/DCOMP 7.1 deliberately has no automatic own-protocol inference."""


def classify_legacy(output):
    output["layout"] = "legacy71"
    output["issues"] = [
        "Leiaute antigo — revisão manual necessária. Não utilizar o protocolo retificado como próprio."
    ]
    return output
