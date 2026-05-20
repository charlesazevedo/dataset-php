#!/usr/bin/env php
<?php
/**
 * Fase 2 — Extração de Snippets e Cálculo de Métricas
 * =====================================================
 * Usa nikic/php-parser para extrair classes, métodos e funções do repositório.
 * Calcula: LOC, Complexidade Ciclomática, Halstead, Profundidade de Aninhamento.
 *
 * Uso:
 *   php fase2_extrair_snippets.php <repo_dir> [output_json] [output_csv]
 *
 * Argumentos:
 *   repo_dir    — Caminho para o repositório clonado
 *   output_json — Arquivo JSON de saída (padrão: ../output/fase2/snippets_com_metricas.json)
 *   output_csv  — Arquivo CSV de saída (padrão: ../output/fase2/snippets_com_metricas.csv)
 *
 * Pré-requisitos:
 *   composer install (executar em ../config/ primeiro)
 */

// Buscar autoload do Composer
$projectDir = dirname(__DIR__);
$autoloadPaths = [
    $projectDir . '/config/vendor/autoload.php',
    __DIR__ . '/../config/vendor/autoload.php',
    __DIR__ . '/../../vendor/autoload.php',
];

$autoloaded = false;
foreach ($autoloadPaths as $path) {
    if (file_exists($path)) {
        require_once $path;
        $autoloaded = true;
        break;
    }
}
if (!$autoloaded) {
    fwrite(STDERR, "ERRO: vendor/autoload.php não encontrado.\n");
    fwrite(STDERR, "Execute: cd config && composer install\n");
    exit(1);
}

use PhpParser\ParserFactory;
use PhpParser\NodeTraverser;
use PhpParser\NodeVisitorAbstract;
use PhpParser\Node;
use PhpParser\PrettyPrinter\Standard as PrettyPrinter;

// ============================================================
// CONFIGURAÇÃO
// ============================================================
$repoPath  = $argv[1] ?? null;
$outputDir = $projectDir . '/output/fase2';

if (!$repoPath) {
    fwrite(STDERR, "Uso: php fase2_extrair_snippets.php <repo_dir> [output.json] [output.csv]\n");
    fwrite(STDERR, "\nExemplo:\n  php scripts/fase2_extrair_snippets.php repos/meu-repo\n");
    exit(1);
}

if (!is_dir($repoPath)) {
    fwrite(STDERR, "ERRO: Diretório não encontrado: $repoPath\n");
    exit(1);
}

$repoPath = realpath($repoPath);
@mkdir($outputDir, 0755, true);

$outputJson = $argv[2] ?? $outputDir . '/snippets_com_metricas.json';
$outputCsv  = $argv[3] ?? $outputDir . '/snippets_com_metricas.csv';

// Detectar nome do repositório
$repoName = basename($repoPath);
$composerFile = $repoPath . '/composer.json';
if (file_exists($composerFile)) {
    $composerData = json_decode(file_get_contents($composerFile), true);
    $repoName = $composerData['name'] ?? $repoName;
}

// Exclusão de diretórios irrelevantes
$excludePatterns = [
    '#/config/#i',
    '#/migrations?/#i',
    '#/routes?/#i',
    '#/factories?/#i',
    '#/seeders?/#i',
    '#/database/(migrations|seeders|factories)/#i',
    '#/vendor/#i',
    '#/node_modules/#i',
    '#/tests?/#i',
    '#\.blade\.php$#i',
    '#/storage/#i',
    '#/bootstrap/cache/#i',
    '#/public/#i',
];

// ============================================================
// HALSTEAD METRICS CALCULATOR
// ============================================================
class HalsteadCalculator
{
    private static $operators = [
        '+', '-', '*', '/', '%', '**',
        '=', '+=', '-=', '*=', '/=', '%=', '**=',
        '.=', '&=', '|=', '^=', '<<=', '>>=',
        '==', '===', '!=', '!==', '<', '>', '<=', '>=', '<=>',
        '&&', '||', '!', 'and', 'or', 'xor', 'not',
        '&', '|', '^', '~', '<<', '>>',
        '++', '--',
        '->', '::', '??', '?:', '?',
        'instanceof', 'new', 'clone',
        'if', 'elseif', 'else', 'switch', 'case', 'default',
        'for', 'foreach', 'while', 'do',
        'break', 'continue', 'return', 'yield', 'throw',
        'try', 'catch', 'finally', 'match',
        '=>', '...', '@', 'fn',
    ];

    public static function calculate(string $code): array
    {
        $tokens = @token_get_all('<?php ' . $code);
        $operators = [];
        $operands = [];

        foreach ($tokens as $token) {
            if (is_array($token)) {
                $tokenValue = $token[1];
                if ($token[0] === T_OPEN_TAG || $token[0] === T_WHITESPACE ||
                    $token[0] === T_COMMENT || $token[0] === T_DOC_COMMENT) continue;

                if (in_array($tokenValue, self::$operators) ||
                    in_array($token[0], [
                        T_IF, T_ELSEIF, T_ELSE, T_SWITCH, T_CASE, T_DEFAULT,
                        T_FOR, T_FOREACH, T_WHILE, T_DO,
                        T_BREAK, T_CONTINUE, T_RETURN, T_THROW,
                        T_TRY, T_CATCH, T_FINALLY,
                        T_NEW, T_CLONE, T_INSTANCEOF,
                        T_LOGICAL_AND, T_LOGICAL_OR, T_LOGICAL_XOR,
                        T_BOOLEAN_AND, T_BOOLEAN_OR,
                        T_IS_EQUAL, T_IS_IDENTICAL, T_IS_NOT_EQUAL, T_IS_NOT_IDENTICAL,
                        T_IS_SMALLER_OR_EQUAL, T_IS_GREATER_OR_EQUAL, T_SPACESHIP,
                        T_INC, T_DEC, T_OBJECT_OPERATOR, T_DOUBLE_COLON,
                        T_COALESCE, T_DOUBLE_ARROW, T_ELLIPSIS,
                        T_PLUS_EQUAL, T_MINUS_EQUAL, T_MUL_EQUAL, T_DIV_EQUAL,
                        T_MOD_EQUAL, T_POW_EQUAL, T_CONCAT_EQUAL,
                        T_AND_EQUAL, T_OR_EQUAL, T_XOR_EQUAL,
                        T_SL_EQUAL, T_SR_EQUAL, T_SL, T_SR, T_POW,
                        T_YIELD, T_YIELD_FROM, T_FN,
                    ])) {
                    $operators[] = $tokenValue;
                } elseif (in_array($token[0], [
                    T_VARIABLE, T_LNUMBER, T_DNUMBER,
                    T_CONSTANT_ENCAPSED_STRING, T_ENCAPSED_AND_WHITESPACE,
                    T_STRING, T_NAME_QUALIFIED, T_NAME_FULLY_QUALIFIED,
                ])) {
                    $operands[] = $tokenValue;
                } elseif ($token[0] === T_FUNCTION || $token[0] === T_CLASS) {
                    $operators[] = $tokenValue;
                }
            } else {
                $char = is_string($token) ? $token : ($token[1] ?? '');
                if (in_array($char, ['+','-','*','/','%','=','<','>','!','&','|','^','~','?','@','.','(',')','[',']','{','}',';',',',':'])) {
                    $operators[] = $char;
                }
            }
        }

        $n1 = count($operators);
        $n2 = count($operands);
        $eta1 = count(array_unique($operators));
        $eta2 = count(array_unique($operands));
        $vocabulary = $eta1 + $eta2;
        $length = $n1 + $n2;

        if ($vocabulary == 0 || $eta2 == 0 || $length == 0) {
            return ['halstead_vocabulary'=>0,'halstead_length'=>0,'halstead_volume'=>0.0,
                    'halstead_difficulty'=>0.0,'halstead_effort'=>0.0,'halstead_time'=>0.0,'halstead_bugs'=>0.0];
        }

        $volume = $length * log($vocabulary, 2);
        $difficulty = ($eta1 / 2) * ($n2 / max($eta2, 1));
        $effort = $volume * $difficulty;

        return [
            'halstead_vocabulary' => $vocabulary,
            'halstead_length' => $length,
            'halstead_volume' => round($volume, 2),
            'halstead_difficulty' => round($difficulty, 2),
            'halstead_effort' => round($effort, 2),
            'halstead_time' => round($effort / 18.0, 2),
            'halstead_bugs' => round($volume / 3000.0, 4),
        ];
    }
}

// ============================================================
// CYCLOMATIC COMPLEXITY (AST)
// ============================================================
class CyclomaticComplexityVisitor extends NodeVisitorAbstract
{
    public int $complexity = 1;

    public function enterNode(Node $node)
    {
        if ($node instanceof Node\Stmt\If_ || $node instanceof Node\Stmt\ElseIf_
            || $node instanceof Node\Stmt\Case_ || $node instanceof Node\Stmt\Catch_
            || $node instanceof Node\Stmt\For_ || $node instanceof Node\Stmt\Foreach_
            || $node instanceof Node\Stmt\While_ || $node instanceof Node\Stmt\Do_) {
            $this->complexity++;
        }
        if ($node instanceof Node\Expr\Ternary || $node instanceof Node\Expr\BinaryOp\Coalesce) {
            $this->complexity++;
        }
        if ($node instanceof Node\Expr\BinaryOp\BooleanAnd || $node instanceof Node\Expr\BinaryOp\BooleanOr
            || $node instanceof Node\Expr\BinaryOp\LogicalAnd || $node instanceof Node\Expr\BinaryOp\LogicalOr) {
            $this->complexity++;
        }
        if ($node instanceof Node\MatchArm && $node->conds !== null) {
            $this->complexity += count($node->conds);
        }
        if ($node instanceof Node\Expr\NullsafeMethodCall || $node instanceof Node\Expr\NullsafePropertyFetch) {
            $this->complexity++;
        }
        return null;
    }
}

// ============================================================
// NESTING DEPTH
// ============================================================
class NestingDepthVisitor extends NodeVisitorAbstract
{
    public int $maxDepth = 0;
    private int $currentDepth = 0;

    private function isNestingNode(Node $node): bool
    {
        return $node instanceof Node\Stmt\If_ || $node instanceof Node\Stmt\ElseIf_
            || $node instanceof Node\Stmt\Else_ || $node instanceof Node\Stmt\For_
            || $node instanceof Node\Stmt\Foreach_ || $node instanceof Node\Stmt\While_
            || $node instanceof Node\Stmt\Do_ || $node instanceof Node\Stmt\Switch_
            || $node instanceof Node\Stmt\TryCatch
            || $node instanceof Node\Expr\Closure || $node instanceof Node\Expr\ArrowFunction;
    }

    public function enterNode(Node $node) {
        if ($this->isNestingNode($node)) {
            $this->currentDepth++;
            $this->maxDepth = max($this->maxDepth, $this->currentDepth);
        }
        return null;
    }

    public function leaveNode(Node $node) {
        if ($this->isNestingNode($node)) { $this->currentDepth--; }
        return null;
    }
}

// ============================================================
// SNIPPET EXTRACTOR
// ============================================================
class SnippetExtractorVisitor extends NodeVisitorAbstract
{
    public array $snippets = [];
    private PrettyPrinter $printer;

    public function __construct() { $this->printer = new PrettyPrinter(); }

    public function enterNode(Node $node)
    {
        if (($node instanceof Node\Stmt\Class_ || $node instanceof Node\Stmt\Trait_) && $node->name) {
            $code = $this->printer->prettyPrint([$node]);
            $this->snippets[] = [
                'type' => $node instanceof Node\Stmt\Trait_ ? 'trait' : 'class',
                'name' => $node->name->toString(),
                'code' => $code, 'start_line' => $node->getStartLine(), 'end_line' => $node->getEndLine(),
                'node' => $node,
                'is_abstract' => $node instanceof Node\Stmt\Class_ && $node->isAbstract(),
                'num_methods' => count(array_filter($node->stmts ?? [], fn($s) => $s instanceof Node\Stmt\ClassMethod)),
                'num_properties' => count(array_filter($node->stmts ?? [], fn($s) => $s instanceof Node\Stmt\Property)),
                'parent_class' => $node instanceof Node\Stmt\Class_ && $node->extends ? $node->extends->toString() : null,
                'implements' => $node instanceof Node\Stmt\Class_ ? array_map(fn($i) => $i->toString(), $node->implements) : [],
            ];
        }

        if ($node instanceof Node\Stmt\Function_) {
            $code = $this->printer->prettyPrint([$node]);
            $this->snippets[] = [
                'type' => 'function', 'name' => $node->name->toString(),
                'code' => $code, 'start_line' => $node->getStartLine(), 'end_line' => $node->getEndLine(),
                'node' => $node,
                'num_parameters' => count($node->params),
                'return_type' => $node->returnType ? $this->typeToString($node->returnType) : null,
            ];
        }
        return null;
    }

    private function typeToString($type): string {
        if ($type instanceof Node\Name) return $type->toString();
        if ($type instanceof Node\Identifier) return $type->toString();
        if ($type instanceof Node\NullableType) return '?' . $this->typeToString($type->type);
        if ($type instanceof Node\UnionType) return implode('|', array_map([$this, 'typeToString'], $type->types));
        if ($type instanceof Node\IntersectionType) return implode('&', array_map([$this, 'typeToString'], $type->types));
        return (string)$type;
    }
}

// ============================================================
// METHOD EXTRACTOR
// ============================================================
class MethodExtractorVisitor extends NodeVisitorAbstract
{
    public array $methods = [];
    private PrettyPrinter $printer;
    private ?string $currentClassName = null;

    public function __construct() { $this->printer = new PrettyPrinter(); }

    public function enterNode(Node $node)
    {
        if ($node instanceof Node\Stmt\Class_ || $node instanceof Node\Stmt\Trait_ || $node instanceof Node\Stmt\Interface_) {
            $this->currentClassName = $node->name ? $node->name->toString() : null;
        }
        if ($node instanceof Node\Stmt\ClassMethod && $this->currentClassName) {
            $code = $this->printer->prettyPrint([$node]);
            $this->methods[] = [
                'type' => 'method',
                'name' => $this->currentClassName . '::' . $node->name->toString(),
                'method_name' => $node->name->toString(),
                'class_name' => $this->currentClassName,
                'code' => $code, 'start_line' => $node->getStartLine(), 'end_line' => $node->getEndLine(),
                'node' => $node,
                'num_parameters' => count($node->params),
                'return_type' => $node->returnType ? $this->typeToString($node->returnType) : null,
                'visibility' => $node->isPublic() ? 'public' : ($node->isProtected() ? 'protected' : 'private'),
                'is_static' => $node->isStatic(),
                'is_abstract' => $node->isAbstract(),
            ];
        }
        return null;
    }

    public function leaveNode(Node $node) {
        if ($node instanceof Node\Stmt\Class_ || $node instanceof Node\Stmt\Trait_ || $node instanceof Node\Stmt\Interface_) {
            $this->currentClassName = null;
        }
        return null;
    }

    private function typeToString($type): string {
        if ($type instanceof Node\Name) return $type->toString();
        if ($type instanceof Node\Identifier) return $type->toString();
        if ($type instanceof Node\NullableType) return '?' . $this->typeToString($type->type);
        if ($type instanceof Node\UnionType) return implode('|', array_map([$this, 'typeToString'], $type->types));
        if ($type instanceof Node\IntersectionType) return implode('&', array_map([$this, 'typeToString'], $type->types));
        return (string)$type;
    }
}

// ============================================================
// UTILITY FUNCTIONS
// ============================================================
function calculateLOC(string $code): array {
    $lines = explode("\n", $code);
    $total = count($lines); $blank = 0; $comment = 0; $inBlock = false;
    foreach ($lines as $line) {
        $t = trim($line);
        if ($t === '') { $blank++; continue; }
        if ($inBlock) { $comment++; if (str_contains($t, '*/')) $inBlock = false; continue; }
        if (str_starts_with($t, '/*')) { $comment++; if (!str_contains($t, '*/')) $inBlock = true; continue; }
        if (str_starts_with($t, '//') || str_starts_with($t, '#')) $comment++;
    }
    return ['loc_total'=>$total, 'loc_blank'=>$blank, 'loc_comment'=>$comment, 'loc_executable'=>$total-$blank-$comment];
}

function calculateCC(Node $node): int {
    $v = new CyclomaticComplexityVisitor();
    $t = new NodeTraverser(); $t->addVisitor($v); $t->traverse([$node]);
    return $v->complexity;
}

function calculateNestingDepth(Node $node): int {
    $v = new NestingDepthVisitor();
    $t = new NodeTraverser(); $t->addVisitor($v); $t->traverse([$node]);
    return $v->maxDepth;
}

function shouldExclude(string $path, array $patterns): bool {
    foreach ($patterns as $p) { if (preg_match($p, $path)) return true; }
    return false;
}

function isGenerated(string $code): bool {
    $markers = ['auto-generated','autogenerated','do not edit','generated by','this file is generated','@generated'];
    $lower = strtolower(substr($code, 0, 500));
    foreach ($markers as $m) { if (str_contains($lower, $m)) return true; }
    return false;
}

function isDeclarationOnly(Node $node): bool {
    if ($node instanceof Node\Stmt\Interface_) return true;
    if ($node instanceof Node\Stmt\Class_ && $node->isAbstract()) {
        foreach ($node->stmts ?? [] as $s) {
            if ($s instanceof Node\Stmt\ClassMethod && !$s->isAbstract() && $s->stmts !== null) return false;
        }
        return true;
    }
    return false;
}

// ============================================================
// MAIN
// ============================================================
fprintf(STDERR, "Fase 2 — Extração de Snippets e Métricas\n");
fprintf(STDERR, "Repositório: $repoPath\n");
fprintf(STDERR, "Repo name:   $repoName\n\n");

$parser = (new ParserFactory())->createForNewestSupportedVersion();
$allSnippets = []; $snippetId = 0; $fileCount = 0; $parseErrors = 0;

$iterator = new RecursiveIteratorIterator(
    new RecursiveDirectoryIterator($repoPath, RecursiveDirectoryIterator::SKIP_DOTS)
);
$phpFiles = [];
foreach ($iterator as $file) {
    if ($file->isFile() && $file->getExtension() === 'php') $phpFiles[] = $file->getPathname();
}

fprintf(STDERR, "Arquivos PHP encontrados: " . count($phpFiles) . "\n");
$progressInterval = max(1, (int)(count($phpFiles) / 20));

foreach ($phpFiles as $idx => $filePath) {
    $relativePath = str_replace($repoPath . '/', '', $filePath);
    if (shouldExclude($relativePath, $excludePatterns)) continue;

    $fileCount++;
    $code = file_get_contents($filePath);
    if (isGenerated($code)) continue;

    try { $ast = $parser->parse($code); if (!$ast) continue; }
    catch (\Throwable $e) { $parseErrors++; continue; }

    // Progresso
    if ($idx % $progressInterval === 0) {
        $pct = round(($idx / count($phpFiles)) * 100);
        fwrite(STDERR, "  Processando... {$pct}%  ($fileCount arquivos válidos)\r");
    }

    $snippetVisitor = new SnippetExtractorVisitor();
    $traverser = new NodeTraverser(); $traverser->addVisitor($snippetVisitor); $traverser->traverse($ast);

    $methodVisitor = new MethodExtractorVisitor();
    $traverser2 = new NodeTraverser(); $traverser2->addVisitor($methodVisitor); $traverser2->traverse($ast);

    // Classes e traits
    foreach ($snippetVisitor->snippets as $s) {
        $node = $s['node']; unset($s['node']);
        if (isDeclarationOnly($node)) continue;
        $loc = calculateLOC($s['code']); $cc = calculateCC($node); $nd = calculateNestingDepth($node);
        $hal = HalsteadCalculator::calculate($s['code']);
        if ($loc['loc_executable'] <= 3 || $cc < 2) continue;

        $snippetId++;
        $allSnippets[] = array_merge(
            ['snippet_id'=>sprintf('SNIPPET_%04d',$snippetId), 'repo'=>$repoName, 'file_path'=>$relativePath,
             'snippet_type'=>$s['type'], 'snippet_name'=>$s['name'], 'start_line'=>$s['start_line'], 'end_line'=>$s['end_line']],
            $loc, ['cyclomatic_complexity'=>$cc, 'nesting_depth'=>$nd], $hal,
            ['num_methods'=>$s['num_methods']??null, 'num_properties'=>$s['num_properties']??null,
             'parent_class'=>$s['parent_class']??null, 'implements'=>isset($s['implements'])?implode(', ',$s['implements']):null,
             'is_abstract'=>$s['is_abstract']??false, 'num_parameters'=>$s['num_parameters']??null,
             'return_type'=>$s['return_type']??null, 'code'=>$s['code']]
        );
    }

    // Métodos
    foreach ($methodVisitor->methods as $m) {
        $node = $m['node']; unset($m['node']);
        if ($m['is_abstract']) continue;
        $loc = calculateLOC($m['code']); $cc = calculateCC($node); $nd = calculateNestingDepth($node);
        $hal = HalsteadCalculator::calculate($m['code']);
        if ($loc['loc_executable'] <= 3 || $cc < 2) continue;

        $snippetId++;
        $allSnippets[] = array_merge(
            ['snippet_id'=>sprintf('SNIPPET_%04d',$snippetId), 'repo'=>$repoName, 'file_path'=>$relativePath,
             'snippet_type'=>$m['type'], 'snippet_name'=>$m['name'], 'start_line'=>$m['start_line'], 'end_line'=>$m['end_line']],
            $loc, ['cyclomatic_complexity'=>$cc, 'nesting_depth'=>$nd], $hal,
            ['num_methods'=>null, 'num_properties'=>null, 'parent_class'=>$m['class_name'],
             'implements'=>null, 'is_abstract'=>false, 'num_parameters'=>$m['num_parameters'],
             'return_type'=>$m['return_type'], 'visibility'=>$m['visibility']??null,
             'is_static'=>$m['is_static']??false, 'code'=>$m['code']]
        );
    }
}

// ============================================================
// OUTPUT
// ============================================================
fprintf(STDERR, "\n\n=== RESUMO DA EXTRAÇÃO ===\n");
fprintf(STDERR, "Arquivos escaneados: $fileCount\n");
fprintf(STDERR, "Erros de parsing: $parseErrors\n");
fprintf(STDERR, "Snippets extraídos (pós-filtro): " . count($allSnippets) . "\n");

$typeCounts = [];
foreach ($allSnippets as $s) { $t = $s['snippet_type']; $typeCounts[$t] = ($typeCounts[$t] ?? 0) + 1; }
foreach ($typeCounts as $type => $count) { fprintf(STDERR, "  - $type: $count\n"); }

// Detectar commit hash
$commitHash = 'unknown';
$headFile = $repoPath . '/.git/HEAD';
if (file_exists($headFile)) {
    $head = trim(file_get_contents($headFile));
    if (str_starts_with($head, 'ref: ')) {
        $refFile = $repoPath . '/.git/' . substr($head, 5);
        if (file_exists($refFile)) $commitHash = trim(file_get_contents($refFile));
    } else {
        $commitHash = $head;
    }
}

// JSON
$jsonOutput = [
    'metadata' => [
        'phase' => 'Fase 2',
        'description' => 'Snippet extraction with software metrics',
        'repo' => $repoName,
        'commit' => $commitHash,
        'extraction_date' => date('c'),
        'total_files_scanned' => $fileCount,
        'parse_errors' => $parseErrors,
        'total_snippets' => count($allSnippets),
        'filters_applied' => [
            'loc_executable_gt' => 3, 'cyclomatic_complexity_gte' => 2,
            'excluded_patterns' => $excludePatterns,
            'excluded_generated_code' => true, 'excluded_declaration_only' => true,
        ],
        'snippet_counts_by_type' => $typeCounts,
    ],
    'snippets' => $allSnippets,
];

file_put_contents($outputJson, json_encode($jsonOutput, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));
fprintf(STDERR, "\nJSON salvo: $outputJson\n");

// CSV
$csvHandle = fopen($outputCsv, 'w');
if (!empty($allSnippets)) {
    $csvFields = ['snippet_id','repo','file_path','snippet_type','snippet_name','start_line','end_line',
        'loc_total','loc_blank','loc_comment','loc_executable','cyclomatic_complexity','nesting_depth',
        'halstead_vocabulary','halstead_length','halstead_volume','halstead_difficulty','halstead_effort',
        'halstead_time','halstead_bugs','num_methods','num_properties','parent_class','implements',
        'is_abstract','num_parameters','return_type','visibility','is_static','code_preview'];
    fputcsv($csvHandle, $csvFields);
    foreach ($allSnippets as $snippet) {
        $row = [];
        foreach ($csvFields as $field) {
            if ($field === 'code_preview') {
                $preview = str_replace(["\n","\r"], [' ',''], $snippet['code'] ?? '');
                $row[] = mb_substr($preview, 0, 200) . (mb_strlen($preview) > 200 ? '...' : '');
            } elseif ($field === 'is_abstract' || $field === 'is_static') {
                $row[] = ($snippet[$field] ?? false) ? '1' : '0';
            } else { $row[] = $snippet[$field] ?? ''; }
        }
        fputcsv($csvHandle, $row);
    }
}
fclose($csvHandle);
fprintf(STDERR, "CSV salvo: $outputCsv\n");
fprintf(STDERR, "\n✓ Fase 2 concluída!\n");
