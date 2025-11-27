import pandas as pd
import os
from django.core.management.base import BaseCommand, CommandError
from collections import defaultdict


class Command(BaseCommand):
    help = "Find duplicate PerDcomps by 'numero per d comp' and orphaned PerDcomps (CNPJs not in Clients) - generate Excel output"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            default="MieleData.xlsx",
            help="Path to input Excel file (default: MieleData.xlsx in project root)",
        )
        parser.add_argument(
            "--output",
            type=str,
            default="perdcomps_duplicates.xlsx",
            help="Path to output Excel file (default: perdcomps_duplicates.xlsx in project root)",
        )
        parser.add_argument(
            "--perdcomps-sheet",
            type=str,
            default="PerDComps",
            help="Name of perdcomps sheet in Excel (default: PerDComps)",
        )
        parser.add_argument(
            "--clients-sheet",
            type=str,
            default="Clients",
            help="Name of clients sheet in Excel (default: Clients)",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Only show summary, suppress detailed output",
        )

    def handle(self, *args, **options):
        input_file = options["file"]
        output_file = options["output"]
        sheet_name = options["perdcomps_sheet"]
        clients_sheet = options["clients_sheet"]
        quiet = options.get("quiet", False)

        # Handle relative paths - make them relative to project root
        if not os.path.isabs(input_file):
            project_root = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            )
            input_file = os.path.join(project_root, input_file)

        if not os.path.isabs(output_file):
            project_root = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            )
            output_file = os.path.join(project_root, output_file)

        # Verify input file exists
        if not os.path.exists(input_file):
            raise CommandError(f"Input Excel file not found: {input_file}")

        if not quiet:
            self.stdout.write(f"Reading PerDcomps from: {input_file}")
            self.stdout.write(f"Sheet: {sheet_name}")

        try:
            # Read the Excel file - PerDcomps sheet
            df = pd.read_excel(input_file, sheet_name=sheet_name)
            if not quiet:
                self.stdout.write(f"Found {len(df)} total PerDcomp records")

            # Read the Clients sheet
            try:
                clients_df = pd.read_excel(input_file, sheet_name=clients_sheet)
                if not quiet:
                    self.stdout.write(f"Found {len(clients_df)} total Client records")
            except ValueError as e:
                self.stdout.write(
                    self.style.WARNING(
                        f"Could not read clients sheet '{clients_sheet}': {e}"
                    )
                )
                self.stdout.write("Will proceed without client validation")
                clients_df = pd.DataFrame()

        except ValueError as e:
            raise CommandError(f"Error reading sheet '{sheet_name}': {e}")
        except Exception as e:
            raise CommandError(f"Error reading Excel file: {e}")

        # Clean and group by numero per d comp
        df_clean = df.copy()

        # Clean the numero per d comp column
        numero_column = "nPerDComp"
        if numero_column not in df_clean.columns:
            raise CommandError(
                f"Column '{numero_column}' not found in sheet. Available columns: {list(df_clean.columns)}"
            )

        # Convert to string and clean
        df_clean[numero_column] = df_clean[numero_column].astype(str).str.strip()

        # Remove rows where numero per d comp is null, empty, or 'nan'
        df_clean = df_clean[
            (df_clean[numero_column] != "nan")
            & (df_clean[numero_column] != "")
            & (df_clean[numero_column].notna())
        ]

        if not quiet:
            self.stdout.write(
                f"After cleaning: {len(df_clean)} records with valid numero PerDcomp"
            )

        # Group by numero per d comp and find duplicates
        grouped = df_clean.groupby(numero_column)
        duplicates_dict = {}

        for numero, group in grouped:
            if len(group) > 1:
                duplicates_dict[numero] = group

        if not duplicates_dict:
            self.stdout.write(self.style.SUCCESS("No duplicates found!"))
            return

        # Create output DataFrame with all duplicates
        all_duplicates = []
        duplicate_summary = []

        for numero, group in duplicates_dict.items():
            # Add all rows for this duplicate numero
            group_with_info = group.copy()
            group_with_info["duplicate_group"] = numero
            group_with_info["duplicate_count"] = len(group)
            group_with_info["row_in_duplicate"] = range(1, len(group) + 1)

            all_duplicates.append(group_with_info)

            # Summary info
            duplicate_summary.append(
                {
                    "numero_perdcomp": numero,
                    "duplicate_count": len(group),
                    "cnpjs": (
                        ", ".join(group["cnpj"].astype(str).unique())
                        if "cnpj" in group.columns
                        else "N/A"
                    ),
                    "first_row_in_original": group.index[0]
                    + 2,  # +2 because Excel starts at 1 and has header
                    "rows_in_original": ", ".join(
                        [str(idx + 2) for idx in group.index]
                    ),
                }
            )

        # Combine all duplicates
        if all_duplicates:
            duplicates_df = pd.concat(all_duplicates, ignore_index=True)

            # Sort by duplicate group and then by original row order
            duplicates_df = duplicates_df.sort_values(
                ["duplicate_group", "row_in_duplicate"]
            )
        else:
            duplicates_df = pd.DataFrame()

        # Create summary DataFrame
        summary_df = pd.DataFrame(duplicate_summary)

        # Find PerDcomps with CNPJs that don't exist in Clients table
        orphaned_perdcomps = pd.DataFrame()
        orphaned_summary = []

        if not clients_df.empty and "cnpj" in df.columns:
            # Clean CNPJ columns for comparison
            df_cnpj_clean = df.copy()
            clients_cnpj_clean = clients_df.copy()

            # Clean CNPJs (remove spaces, convert to string)
            df_cnpj_clean["cnpj_clean"] = (
                df_cnpj_clean["cnpj"].astype(str).str.strip().str.replace(" ", "")
            )
            clients_cnpj_clean["cnpj_clean"] = (
                clients_cnpj_clean["cnpj"].astype(str).str.strip().str.replace(" ", "")
                if "cnpj" in clients_cnpj_clean.columns
                else pd.Series()
            )

            # Get unique CNPJs from clients
            if "cnpj" in clients_cnpj_clean.columns:
                valid_cnpjs = set(clients_cnpj_clean["cnpj_clean"].dropna().unique())

                # Find PerDcomps with CNPJs not in clients table
                orphaned_mask = ~df_cnpj_clean["cnpj_clean"].isin(valid_cnpjs)
                orphaned_perdcomps = df[orphaned_mask].copy()

                if not orphaned_perdcomps.empty:
                    # Add additional info
                    orphaned_perdcomps["reason"] = "CNPJ not found in Clients table"
                    orphaned_perdcomps["original_row"] = (
                        orphaned_perdcomps.index + 2
                    )  # +2 for Excel row number

                    # Create summary of orphaned CNPJs
                    orphaned_cnpj_counts = orphaned_perdcomps["cnpj"].value_counts()
                    for cnpj, count in orphaned_cnpj_counts.items():
                        orphaned_summary.append(
                            {
                                "cnpj": cnpj,
                                "perdcomp_count": count,
                                "first_perdcomp": orphaned_perdcomps[
                                    orphaned_perdcomps["cnpj"] == cnpj
                                ]
                                .iloc[0]
                                .get("nPerDComp", "N/A"),
                                "reason": "CNPJ not found in Clients table",
                            }
                        )

                if not quiet:
                    self.stdout.write(
                        f"Found {len(orphaned_perdcomps)} PerDcomps with CNPJs not in Clients table"
                    )
            else:
                if not quiet:
                    self.stdout.write(
                        "No 'cnpj' column found in Clients sheet, skipping orphan check"
                    )
        else:
            if not quiet:
                self.stdout.write(
                    "Clients data not available or no 'cnpj' column in PerDcomps, skipping orphan check"
                )

        orphaned_summary_df = pd.DataFrame(orphaned_summary)

        if not quiet:
            self.stdout.write(
                f"Found {len(duplicates_dict)} unique numero PerDcomp with duplicates"
            )
            self.stdout.write(f"Total duplicate records: {len(duplicates_df)}")

        # Write to Excel with multiple sheets
        try:
            with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
                # Sheet 1: All duplicate records with original data
                duplicates_df.to_excel(
                    writer, sheet_name="Duplicate_Records", index=False
                )

                # Sheet 2: Summary of duplicates
                summary_df.to_excel(writer, sheet_name="Duplicate_Summary", index=False)

                # Sheet 3: Orphaned PerDcomps (CNPJs not in Clients)
                if not orphaned_perdcomps.empty:
                    orphaned_perdcomps.to_excel(
                        writer, sheet_name="Orphaned_PerDcomps", index=False
                    )
                    orphaned_summary_df.to_excel(
                        writer, sheet_name="Orphaned_Summary", index=False
                    )

                # Sheet 4: Statistics
                stats_data = {
                    "Metric": [
                        "Total Records in Original File",
                        "Records with Valid numero PerDcomp",
                        "Unique numero PerDcomp Values",
                        "numero PerDcomp with Duplicates",
                        "Total Duplicate Records",
                        "Percentage of Records that are Duplicates",
                        "PerDcomps with CNPJs not in Clients",
                        "Unique CNPJs not in Clients table",
                    ],
                    "Value": [
                        len(df),
                        len(df_clean),
                        len(df_clean[numero_column].unique()),
                        len(duplicates_dict),
                        len(duplicates_df),
                        (
                            f"{(len(duplicates_df) / len(df_clean) * 100):.2f}%"
                            if len(df_clean) > 0
                            else "0%"
                        ),
                        len(orphaned_perdcomps),
                        len(orphaned_summary_df),
                    ],
                }
                stats_df = pd.DataFrame(stats_data)
                stats_df.to_excel(writer, sheet_name="Statistics", index=False)

            self.stdout.write(self.style.SUCCESS(f"Output file created: {output_file}"))

            if not quiet:
                sheet_count = 3
                self.stdout.write(
                    f"\nFile contains {sheet_count + (2 if not orphaned_perdcomps.empty else 0)} sheets:"
                )
                self.stdout.write(
                    "  1. 'Duplicate_Records' - All duplicate records with original data"
                )
                self.stdout.write(
                    "  2. 'Duplicate_Summary' - Summary by numero PerDcomp"
                )
                if not orphaned_perdcomps.empty:
                    self.stdout.write(
                        "  3. 'Orphaned_PerDcomps' - PerDcomps with CNPJs not in Clients table"
                    )
                    self.stdout.write(
                        "  4. 'Orphaned_Summary' - Summary of orphaned CNPJs"
                    )
                    self.stdout.write(
                        f"  {sheet_count + 2}. 'Statistics' - Overall statistics"
                    )
                else:
                    self.stdout.write("  3. 'Statistics' - Overall statistics")

            # Print summary to console
            self.stdout.write("\n" + "=" * 50)
            self.stdout.write("DUPLICATE SUMMARY:")
            self.stdout.write("=" * 50)

            for _, row in summary_df.head(10).iterrows():  # Show first 10
                self.stdout.write(
                    f"numero PerDcomp: {row['numero_perdcomp']} "
                    f"(found {row['duplicate_count']} times)"
                )
                if not quiet:
                    self.stdout.write(f"  CNPJs: {row['cnpjs']}")
                    self.stdout.write(f"  Original rows: {row['rows_in_original']}")

            if len(summary_df) > 10:
                self.stdout.write(
                    f"\n... and {len(summary_df) - 10} more duplicate groups"
                )

            # Print orphaned CNPJs summary
            if not orphaned_summary_df.empty:
                self.stdout.write("\n" + "=" * 50)
                self.stdout.write("ORPHANED PERDCOMPS SUMMARY:")
                self.stdout.write("=" * 50)

                for _, row in orphaned_summary_df.head(10).iterrows():
                    self.stdout.write(
                        f"CNPJ: {row['cnpj']} "
                        f"({row['perdcomp_count']} PerDcomps not linked to any client)"
                    )
                    if not quiet:
                        self.stdout.write(f"  First PerDcomp: {row['first_perdcomp']}")

                if len(orphaned_summary_df) > 10:
                    self.stdout.write(
                        f"\n... and {len(orphaned_summary_df) - 10} more orphaned CNPJs"
                    )

            if len(summary_df) > 10 or not orphaned_summary_df.empty:
                self.stdout.write("\nCheck the output Excel file for complete details.")

        except Exception as e:
            raise CommandError(f"Error writing output file: {e}")
